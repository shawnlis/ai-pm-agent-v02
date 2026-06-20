from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.factors import (
    ACCOUNTING_RISK_BLOCKER,
    MISSING_VALUATION_TOP_PICK_BLOCKER,
    PRICED_IN_PENALTY_REASON,
    SOURCE_METADATA_GAP,
    STALE_MARKET_DATA_BLOCKER,
    WEAK_EVIDENCE_CAP,
)
from ai_pm_agent.autopm.models import StockPickerScore
from ai_pm_agent.autopm.stock_picker import BLOCKED, TOP_PICK, WATCHLIST, rank_stocks, score_stock


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "autopm_stock_picker" / "generic_cases_v01.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["rows"]


def _case(ticker: str) -> dict[str, object]:
    return next(row for row in _cases() if row["ticker"] == ticker)


def test_strong_fixture_company_ranks_top_pick() -> None:
    ranking = rank_stocks(_cases())

    assert ranking[0].ticker == "HQAI"
    assert ranking[0].tier == TOP_PICK
    assert ranking[0].rank == 1
    assert ranking[0].total_score >= 0.75
    assert ranking[0].source_hashes == ("src-hqai-2026q1",)
    assert ranking[0].not_recommendation_until_recommender is True


def test_missing_valuation_blocks_top_pick() -> None:
    result = score_stock(_case("NOVAL"))

    assert result.tier != TOP_PICK
    assert MISSING_VALUATION_TOP_PICK_BLOCKER in result.reason_codes
    assert MISSING_VALUATION_TOP_PICK_BLOCKER in result.data_gaps
    assert "valuation snapshot" in result.required_next_evidence


def test_stale_market_data_reduces_score_and_blocks_top_pick() -> None:
    result = score_stock(_case("STALE"))

    assert result.tier != TOP_PICK
    assert STALE_MARKET_DATA_BLOCKER in result.reason_codes
    assert result.factor_scores["valuation_attractiveness_score"] == 0.0
    assert result.factor_scores["momentum_technical_score"] == 0.0


def test_weak_evidence_caps_score() -> None:
    result = score_stock(_case("WEAK"))

    assert result.total_score <= WEAK_EVIDENCE_CAP
    assert result.tier == WATCHLIST
    assert "WEAK_EVIDENCE_SCORE_CAP" in result.reason_codes
    assert "stronger primary or official evidence" in result.required_next_evidence


def test_accounting_risk_blocks_top_pick() -> None:
    result = score_stock(_case("ACCT"))

    assert result.tier == BLOCKED
    assert ACCOUNTING_RISK_BLOCKER in result.reason_codes
    assert result.red_flags


def test_price_move_outpacing_revision_triggers_penalty() -> None:
    result = score_stock(_case("PRICEY"))

    assert PRICED_IN_PENALTY_REASON in result.reason_codes
    assert result.factor_scores["crowding_priced_in_risk"] >= 0.7
    assert "price move outpaces earnings revision" in result.red_flags


def test_missing_source_metadata_creates_data_gap() -> None:
    result = score_stock(_case("NOSRC"))

    assert SOURCE_METADATA_GAP in result.data_gaps
    assert "source metadata for ranking reasons" in result.required_next_evidence


def test_ranking_is_deterministic() -> None:
    first = [row.to_dict() for row in rank_stocks(_cases())]
    second = [row.to_dict() for row in rank_stocks(list(reversed(_cases())))]

    assert first == second


def test_output_is_compatible_with_stock_picker_score_schema() -> None:
    result = score_stock(_case("HQAI"), rank=1).to_stock_picker_score()

    assert isinstance(result, StockPickerScore)
    assert result.score >= 0.75
    assert result.tier == TOP_PICK


def test_no_portfolio_context_or_pm_instruction_fields_are_emitted() -> None:
    row = dict(_case("HQAI"))
    row["current_weight_pct"] = 99.0
    result = score_stock(row).to_dict()

    forbidden_fields = {
        "action",
        "target" + "_weight_pct",
        "current" + "_weight_pct",
        "delta" + "_weight_pct",
        "max_position" + "_pct",
    }
    assert forbidden_fields.isdisjoint(result)
    assert result["total_score"] == score_stock(_case("HQAI")).total_score


def test_stock_picker_performs_no_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert score_stock(_case("HQAI")).ticker == "HQAI"


def test_no_autopm_module_imports_broker_or_execution_modules() -> None:
    autopm_root = Path("src/ai_pm_agent/autopm")
    forbidden_import_terms = ("broker", "ibkr", "execution")
    offenders: list[str] = []

    for path in autopm_root.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in forbidden_import_terms):
                offenders.append(f"{path}:{line}")

    assert offenders == []

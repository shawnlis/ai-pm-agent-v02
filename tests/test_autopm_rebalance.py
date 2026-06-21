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

from ai_pm_agent.autopm.models import AutopmMode
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.rebalance import ExposureSnapshot, build_rebalance_proposal


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "autopm_rebalance" / "sample_inputs.json"
SOURCE_HASH = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["source_hash"]


def _policy(**overrides: object) -> AutopmPolicy:
    row = {
        "mode": AutopmMode.PROPOSAL,
        "max_single_name_weight_pct": 5.0,
        "max_theme_weight_pct": 35.0,
        "max_region_weight_pct": 80.0,
        "max_leverage_adjusted_exposure_pct": 120.0,
        "min_cash_pct": 2.0,
        "max_new_position_pct": 3.0,
        "max_add_pct_per_run": 2.0,
        "sell_allowed": True,
    }
    row.update(overrides)
    return AutopmPolicy(**row)


def _reason() -> list[dict[str, str]]:
    return [
        {
            "code": "AI_REVENUE_MIGRATION_EVIDENCED",
            "backing_type": "source",
            "source_hash": SOURCE_HASH,
            "evidence_level": "primary_official",
            "source_date": "2026-03-31",
            "period": "2026Q1",
            "field": "ai_revenue_share",
        }
    ]


def _rec(ticker: str, action: str, current: float, target: float, **overrides: object) -> dict[str, object]:
    row = {
        "ticker": ticker,
        "action": action,
        "conviction_score": 0.82,
        "current_weight_pct": current,
        "target_weight_pct": target,
        "delta_weight_pct": round(target - current, 4),
        "max_position_pct": 5.0,
        "reason_codes": _reason(),
        "risk_warnings": [],
        "blocked_by": [],
        "claim_audit_passed": True,
        "source_hashes": [SOURCE_HASH],
        "theme": "AI hardware",
        "region": "Asia",
        "sector": "Information Technology",
        "issuer": ticker,
        "valuation_gate": {"passed": True},
        "portfolio_gate": {"passed": True},
        "thesis_kill_triggers": ["kill1", "kill2", "kill3"],
    }
    row.update(overrides)
    return row


def _before() -> ExposureSnapshot:
    return ExposureSnapshot(
        theme={"AI hardware": 28.0},
        region={"Asia": 28.0},
        sector={"Information Technology": 28.0},
        issuer={"TRIM": 8.0},
        leverage_adjusted_exposure_pct=90.0,
    )


def test_proposal_respects_max_single_name_cap() -> None:
    result = build_rebalance_proposal(
        [_rec("NEWAI", "add", 4.0, 8.0)],
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=_before(),
        policy=_policy(),
    )

    row = result.proposal.proposed_trades[0]
    assert row["target_weight_pct"] == 5.0
    assert row["not_executed"] is True


def test_proposal_respects_cash_and_min_cash() -> None:
    result = build_rebalance_proposal(
        [_rec("NEWAI", "buy", 0.0, 9.0, max_position_pct=9.0)],
        as_of_date="2026-06-21",
        starting_cash_pct=3.0,
        exposure_before=_before(),
        policy=_policy(max_single_name_weight_pct=9.0, max_new_position_pct=9.0),
    )

    row = result.proposal.proposed_trades[0]
    assert row["target_weight_pct"] == 1.0
    assert "MIN_CASH_LIMIT_EXCEEDED" in row["blocked_by"]
    assert result.proposal.ending_cash_pct == 3.0


def test_proposal_respects_theme_exposure_cap() -> None:
    result = build_rebalance_proposal(
        [_rec("NEWAI", "buy", 0.0, 3.0)],
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=ExposureSnapshot(theme={"AI hardware": 34.0}, region={"Asia": 28.0}),
        policy=_policy(max_theme_weight_pct=35.0),
    )

    row = result.proposal.proposed_trades[0]
    assert row["target_weight_pct"] == 1.0
    assert "THEME_EXPOSURE_LIMIT_EXCEEDED" in row["blocked_by"]
    assert result.exposure_after.theme["AI hardware"] == 35.0


def test_proposal_respects_region_exposure_cap() -> None:
    result = build_rebalance_proposal(
        [_rec("NEWAI", "buy", 0.0, 3.0)],
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=ExposureSnapshot(theme={"AI hardware": 10.0}, region={"Asia": 79.0}),
        policy=_policy(max_region_weight_pct=80.0),
    )

    row = result.proposal.proposed_trades[0]
    assert row["target_weight_pct"] == 1.0
    assert "REGION_EXPOSURE_LIMIT_EXCEEDED" in row["blocked_by"]
    assert result.exposure_after.region["Asia"] == 80.0


def test_trims_and_sells_can_fund_buys_as_proposal_math() -> None:
    result = build_rebalance_proposal(
        [
            _rec("TRIM", "trim", 8.0, 5.0),
            _rec("NEWAI", "buy", 0.0, 3.0),
        ],
        as_of_date="2026-06-21",
        starting_cash_pct=2.0,
        exposure_before=_before(),
        policy=_policy(),
    )

    rows = {row["ticker"]: row for row in result.proposal.proposed_trades}
    assert rows["TRIM"]["delta_weight_pct"] == -3.0
    assert rows["NEWAI"]["target_weight_pct"] == 3.0
    assert result.proposal.ending_cash_pct == 2.0


def test_blocked_and_manual_review_rows_are_non_executable() -> None:
    result = build_rebalance_proposal(
        [
            _rec("BLOCK", "add", 2.0, 4.0, blocked_by=["THEME_EXPOSURE_LIMIT_EXCEEDED"]),
            _rec("REVIEW", "manual_review", 1.0, 3.0, claim_audit_passed=False),
        ],
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=_before(),
        policy=_policy(),
    )

    for row in result.proposal.proposed_trades:
        assert row["not_executed"] is True
        assert row["executable_proposal"] is False
    assert len(result.proposal.blocked_recommendations) == 2


def test_exposure_before_after_summaries_update_for_executable_proposals() -> None:
    result = build_rebalance_proposal(
        [_rec("NEWAI", "buy", 0.0, 3.0)],
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=_before(),
        policy=_policy(),
    )

    payload = result.to_dict()
    assert payload["theme_exposure_before_after"]["AI hardware"]["before"] == 28.0
    assert payload["theme_exposure_before_after"]["AI hardware"]["after"] == 31.0
    assert payload["region_exposure_before_after"]["Asia"]["after"] == 31.0
    assert payload["sector_exposure_before_after"]["Information Technology"]["after"] == 31.0
    assert payload["issuer_exposure_before_after"]["NEWAI"]["after"] == 3.0


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert build_rebalance_proposal([_rec("NEWAI", "buy", 0.0, 3.0)], as_of_date="2026-06-21", starting_cash_pct=10.0).proposal.not_executed is True


def test_no_broker_execution_imports_or_cli_files() -> None:
    for path in [Path("src/ai_pm_agent/autopm/rebalance.py")]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")):
                assert "broker" not in stripped
                assert "ibkr" not in stripped
                assert "execution" not in stripped
    assert not Path("src/ai_pm_agent/cli/autopm.py").exists()
    assert not Path("scripts/autopm.py").exists()

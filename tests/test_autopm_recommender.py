from __future__ import annotations

from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import (
    AutopmMode,
    EvidenceGateResult,
    PortfolioGateResult,
    RecommendationAction,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.portfolio_policy import AutopmPortfolioPolicy
from ai_pm_agent.autopm.recommender import SourceReference, recommend_from_score


SOURCE_HASH = "src-recommender-fixture"


def _source_manifest() -> dict[str, object]:
    return {
        "sources": [
            {
                "source_hash": SOURCE_HASH,
                "source_date": "2026-03-31",
                "period": "2026Q1",
                "evidence_level": "primary_official",
                "stale": False,
                "warning_codes": [],
            }
        ]
    }


def _source_refs() -> tuple[SourceReference, ...]:
    return (
        SourceReference(
            code="AI_REVENUE_MIGRATION_EVIDENCED",
            source_hash=SOURCE_HASH,
            evidence_level="primary_official",
            source_date="2026-03-31",
            period="2026Q1",
            field="ai_revenue_share",
        ),
    )


def _score(**overrides: object) -> StockPickerScore:
    row = {
        "ticker": "NEWAI",
        "company_name": "Synthetic New AI",
        "market": "fixture",
        "rank": 1,
        "score": 0.86,
        "tier": "top_pick",
        "factor_scores": {
            "business_quality_score": 0.85,
            "growth_quality_score": 0.84,
            "valuation_attractiveness_score": 0.8,
            "momentum_technical_score": 0.72,
            "balance_sheet_quality_score": 0.82,
        },
        "reason_codes": ("RANKING_TOP_TIER",),
        "data_gaps": (),
        "red_flags": (),
        "required_next_evidence": (),
    }
    row.update(overrides)
    return StockPickerScore(**row)


def _policy(**overrides: object) -> AutopmPortfolioPolicy:
    base = AutopmPolicy(
        mode=AutopmMode.PROPOSAL,
        max_single_name_weight_pct=5.0,
        max_theme_weight_pct=35.0,
        max_region_weight_pct=80.0,
        max_leverage_adjusted_exposure_pct=120.0,
        min_cash_pct=2.0,
        max_new_position_pct=3.0,
        max_add_pct_per_run=2.0,
        trim_threshold_pct=1.0,
        sell_allowed=bool(overrides.pop("sell_allowed", False)),
    )
    return AutopmPortfolioPolicy(base_policy=base, max_sector_weight_pct=60.0)


def _rec(**overrides: object):
    row = {
        "score": _score(),
        "current_weight_pct": 0.0,
        "portfolio_gate": PortfolioGateResult(True, 0.9, current_weight_pct=0.0, max_position_pct=5.0),
        "evidence_gate": EvidenceGateResult(True, 0.92, reason_codes=("EVIDENCE_OK",)),
        "valuation_gate": ValuationGateResult(True, 0.86, valuation_basis="fixture valuation"),
        "risk_gate": RiskGateResult(True, 0.88),
        "red_team": RedTeamResult(True, thesis_kill_triggers=("lost customer", "margin break", "valuation break")),
        "source_refs": _source_refs(),
        "source_manifest": _source_manifest(),
        "policy": _policy(),
        "market_data_stale": False,
    }
    row.update(overrides)
    return recommend_from_score(**row)


def test_high_ranked_zero_weight_name_becomes_buy_with_target_weight() -> None:
    rec = _rec()

    assert rec.action == RecommendationAction.BUY
    assert 0 < rec.target_weight_pct <= 3.0
    assert rec.target_weight_pct <= rec.max_position_pct
    assert rec.delta_weight_pct == rec.target_weight_pct
    assert rec.thesis_kill_triggers
    assert rec.claim_audit_passed is True


def test_existing_high_ranked_underweight_name_becomes_add() -> None:
    rec = _rec(current_weight_pct=2.0, portfolio_gate=PortfolioGateResult(True, 0.9, current_weight_pct=2.0, max_position_pct=5.0))

    assert rec.action == RecommendationAction.ADD
    assert rec.target_weight_pct > rec.current_weight_pct
    assert rec.target_weight_pct <= 4.0
    assert rec.claim_audit_passed is True


def test_existing_overweight_name_holds_when_trim_not_allowed() -> None:
    rec = _rec(
        current_weight_pct=6.0,
        portfolio_gate=PortfolioGateResult(True, 0.9, current_weight_pct=6.0, max_position_pct=8.0),
        policy=_policy(sell_allowed=False),
    )

    assert rec.action == RecommendationAction.HOLD
    assert rec.target_weight_pct <= rec.current_weight_pct


def test_broken_thesis_sells_only_if_policy_allows() -> None:
    red_team = RedTeamResult(False, thesis_kill_triggers=("lost customer",), warning_codes=("THESIS_KILL_TRIGGER_ACTIVATED",))

    blocked = _rec(current_weight_pct=4.0, red_team=red_team, policy=_policy(sell_allowed=False))
    allowed = _rec(current_weight_pct=4.0, red_team=red_team, policy=_policy(sell_allowed=True))

    assert blocked.action == RecommendationAction.MANUAL_REVIEW
    assert allowed.action == RecommendationAction.SELL
    assert allowed.target_weight_pct == 0.0


def test_weak_evidence_becomes_watch_or_manual_review() -> None:
    rec = _rec(evidence_gate=EvidenceGateResult(False, 0.35, required_next_evidence=("primary evidence",)))

    assert rec.action in {RecommendationAction.WATCH, RecommendationAction.MANUAL_REVIEW}
    assert rec.action not in {RecommendationAction.BUY, RecommendationAction.ADD}


def test_missing_valuation_and_stale_market_data_do_not_buy_or_add() -> None:
    missing = _rec(valuation_gate=ValuationGateResult(False, 0.0, warning_codes=("VALUATION_DATA_MISSING",)))
    stale = _rec(market_data_stale=True)

    assert missing.action not in {RecommendationAction.BUY, RecommendationAction.ADD}
    assert stale.action not in {RecommendationAction.BUY, RecommendationAction.ADD}


def test_concentration_breach_blocks_add() -> None:
    gate = PortfolioGateResult(False, 0.4, current_weight_pct=2.0, max_position_pct=5.0, concentration_warnings=("THEME_EXPOSURE_LIMIT_EXCEEDED",))
    rec = _rec(current_weight_pct=2.0, portfolio_gate=gate)

    assert rec.action == RecommendationAction.HOLD
    assert rec.delta_weight_pct == 0.0
    assert "THEME_EXPOSURE_LIMIT_EXCEEDED" in rec.risk_warnings


def test_recommendation_has_source_backed_reason_codes_and_model_projection() -> None:
    rec = _rec()
    model = rec.to_portfolio_aware_recommendation()

    assert rec.reason_codes[0]["source_hash"] == SOURCE_HASH
    assert rec.reason_codes[0]["evidence_level"] == "primary_official"
    assert model.action == rec.action
    assert model.delta_weight_pct == rec.delta_weight_pct


def test_strict_claim_audit_failure_downgrades_to_manual_review() -> None:
    rec = _rec(source_refs=())

    assert rec.action == RecommendationAction.MANUAL_REVIEW
    assert rec.claim_audit_passed is True
    assert "REASON_CODES_MISSING" in rec.risk_warnings


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert _rec().ticker == "NEWAI"


def test_no_legacy_pm_prompt_or_broker_execution_imports() -> None:
    for path in Path("src/ai_pm_agent/autopm").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "build_pm_prompt" not in text
        for line in text.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")):
                assert "broker" not in stripped
                assert "ibkr" not in stripped
                assert "execution" not in stripped

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import (
    AutopmMode,
    EvidenceGateResult,
    PortfolioGateResult,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.portfolio_policy import AutopmPortfolioPolicy
from ai_pm_agent.autopm.sizing import SizingInputs, size_position


def _score(**overrides: object) -> StockPickerScore:
    row = {
        "ticker": "NEWAI",
        "company_name": "Synthetic New AI",
        "market": "fixture",
        "rank": 1,
        "score": 0.82,
        "tier": "top_pick",
        "factor_scores": {
            "business_quality_score": 0.85,
            "growth_quality_score": 0.8,
            "valuation_attractiveness_score": 0.78,
            "momentum_technical_score": 0.7,
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


def _inputs(**overrides: object) -> SizingInputs:
    row = {
        "score": _score(),
        "current_weight_pct": 0.0,
        "portfolio_gate": PortfolioGateResult(True, 0.9, current_weight_pct=0.0, max_position_pct=5.0),
        "evidence_gate": EvidenceGateResult(True, 0.9, reason_codes=("EVIDENCE_OK",)),
        "valuation_gate": ValuationGateResult(True, 0.85, valuation_basis="fixture valuation"),
        "risk_gate": RiskGateResult(True, 0.85),
        "red_team": RedTeamResult(True, thesis_kill_triggers=("kill1", "kill2", "kill3")),
        "policy": _policy(),
        "market_data_stale": False,
    }
    row.update(overrides)
    return SizingInputs(**row)


def test_zero_current_weight_target_respects_new_position_cap() -> None:
    result = size_position(_inputs())

    assert 0 < result.decision.target_weight_pct <= 3.0
    assert result.decision.target_weight_pct <= result.decision.max_position_pct
    assert result.decision.delta_weight_pct == result.decision.target_weight_pct


def test_underweight_existing_name_respects_add_cap() -> None:
    result = size_position(_inputs(current_weight_pct=2.0))

    assert result.decision.target_weight_pct > 2.0
    assert result.decision.target_weight_pct <= 4.0
    assert round(result.decision.target_weight_pct - 2.0, 4) == result.decision.delta_weight_pct


def test_weak_evidence_blocks_add_style_sizing() -> None:
    result = size_position(_inputs(evidence_gate=EvidenceGateResult(False, 0.35, required_next_evidence=("primary evidence",))))

    assert result.decision.target_weight_pct == 0.0
    assert "EVIDENCE_GATE_FAILED" in result.blocked_by


def test_missing_valuation_blocks_buy_add_sizing() -> None:
    result = size_position(_inputs(valuation_gate=ValuationGateResult(False, 0.0, warning_codes=("VALUATION_DATA_MISSING",))))

    assert result.decision.target_weight_pct == 0.0
    assert "VALUATION_GATE_FAILED" in result.blocked_by


def test_stale_market_data_blocks_sizing() -> None:
    result = size_position(_inputs(market_data_stale=True))

    assert result.decision.target_weight_pct == 0.0
    assert "STALE_MARKET_DATA" in result.blocked_by


def test_portfolio_concentration_blocks_add() -> None:
    gate = PortfolioGateResult(False, 0.4, current_weight_pct=2.0, max_position_pct=5.0, concentration_warnings=("THEME_EXPOSURE_LIMIT_EXCEEDED",))
    result = size_position(_inputs(current_weight_pct=2.0, portfolio_gate=gate))

    assert result.decision.target_weight_pct == 2.0
    assert result.decision.delta_weight_pct == 0.0
    assert "PORTFOLIO_GATE_FAILED" in result.blocked_by
    assert "THEME_EXPOSURE_LIMIT_EXCEEDED" in result.risk_warnings


def test_broken_thesis_sell_only_when_policy_allows() -> None:
    red_team = RedTeamResult(False, thesis_kill_triggers=("lost customer",), warning_codes=("THESIS_KILL_TRIGGER_ACTIVATED",))

    blocked = size_position(_inputs(current_weight_pct=4.0, red_team=red_team, policy=_policy(sell_allowed=False)))
    allowed = size_position(_inputs(current_weight_pct=4.0, red_team=red_team, policy=_policy(sell_allowed=True)))

    assert blocked.decision.target_weight_pct == 4.0
    assert allowed.decision.target_weight_pct == 0.0


def test_delta_weight_always_equals_target_minus_current() -> None:
    result = size_position(_inputs(current_weight_pct=1.5))

    assert result.decision.delta_weight_pct == round(result.decision.target_weight_pct - result.decision.current_weight_pct, 4)

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import (
    AUTOPM_SCHEMA_VERSION,
    AutopmMode,
    AutopmRunManifest,
    DataProviderLevel,
    EvidenceGateResult,
    PortfolioAwareRecommendation,
    PortfolioGateResult,
    PositionSizingDecision,
    RebalanceProposal,
    RecommendationAction,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)


def _field_names(model: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(model))


def test_schema_version_is_stable() -> None:
    assert AUTOPM_SCHEMA_VERSION == "autopm.v0.1"


def test_default_autopm_mode_disabled() -> None:
    manifest = AutopmRunManifest(run_id="fixture-run")

    assert manifest.mode == AutopmMode.DISABLED


def test_mode_enum_values_are_stable() -> None:
    assert [mode.value for mode in AutopmMode] == [
        "disabled",
        "proposal",
        "paper",
        "live_recommendation",
    ]


def test_provider_level_enum_values_are_stable() -> None:
    assert [level.value for level in DataProviderLevel] == [
        "LEVEL_0_FIXTURE",
        "LEVEL_1_PUBLIC_OFFICIAL",
        "LEVEL_2_MARKET_DATA_VENDOR",
        "LEVEL_3_BROKER_READ_ONLY",
        "LEVEL_4_PAPER_TRADING",
        "LEVEL_5_LIVE_EXECUTION",
    ]


def test_recommendation_action_enum_values_are_stable() -> None:
    assert [action.value for action in RecommendationAction] == [
        "buy",
        "add",
        "hold",
        "trim",
        "sell",
        "avoid",
        "watch",
        "manual_review",
    ]


def test_recommendation_actions_are_distinct_from_review_first_statuses() -> None:
    review_first_statuses = {"OPPORTUNITY_REVIEW", "MONITOR", "INSUFFICIENT_EVIDENCE"}

    assert not review_first_statuses.intersection({action.value for action in RecommendationAction})


def test_stock_picker_score_fields_are_stable() -> None:
    assert _field_names(StockPickerScore) == (
        "ticker",
        "company_name",
        "market",
        "rank",
        "score",
        "tier",
        "factor_scores",
        "reason_codes",
        "data_gaps",
        "red_flags",
        "required_next_evidence",
        "schema_version",
    )


def test_portfolio_aware_recommendation_fields_are_stable() -> None:
    assert _field_names(PortfolioAwareRecommendation) == (
        "ticker",
        "company_name",
        "market",
        "action",
        "rating",
        "conviction_score",
        "current_weight_pct",
        "target_weight_pct",
        "delta_weight_pct",
        "max_position_pct",
        "evidence_score",
        "valuation_score",
        "quality_score",
        "momentum_score",
        "risk_score",
        "portfolio_fit_score",
        "reason_codes",
        "risk_warnings",
        "thesis_kill_triggers",
        "required_next_evidence",
        "not_personal_financial_advice",
        "schema_version",
    )


def test_foundation_model_fields_are_stable() -> None:
    assert _field_names(PositionSizingDecision) == (
        "ticker",
        "current_weight_pct",
        "target_weight_pct",
        "delta_weight_pct",
        "max_position_pct",
        "reason_codes",
        "blocked_by",
        "schema_version",
    )
    assert _field_names(RebalanceProposal) == (
        "as_of_date",
        "starting_cash_pct",
        "ending_cash_pct",
        "proposed_trades",
        "blocked_recommendations",
        "not_executed",
        "schema_version",
    )
    assert _field_names(EvidenceGateResult) == (
        "passed",
        "score",
        "reason_codes",
        "warning_codes",
        "required_next_evidence",
    )
    assert _field_names(ValuationGateResult) == (
        "passed",
        "score",
        "valuation_basis",
        "reason_codes",
        "warning_codes",
    )
    assert _field_names(RiskGateResult) == (
        "passed",
        "score",
        "risk_warnings",
        "reason_codes",
    )
    assert _field_names(PortfolioGateResult) == (
        "passed",
        "portfolio_fit_score",
        "current_weight_pct",
        "max_position_pct",
        "concentration_warnings",
        "reason_codes",
    )
    assert _field_names(RedTeamResult) == (
        "passed",
        "strongest_bear_case",
        "missing_evidence",
        "thesis_kill_triggers",
        "downgrade_triggers",
        "warning_codes",
    )

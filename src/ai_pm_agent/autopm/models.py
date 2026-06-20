"""Stable autopm schema objects.

These models are foundation-only. They describe future autopm artifacts but do
not calculate recommendations, load live data, connect to brokers, or execute
orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


AUTOPM_SCHEMA_VERSION = "autopm.v0.1"


class AutopmMode(StrEnum):
    DISABLED = "disabled"
    PROPOSAL = "proposal"
    PAPER = "paper"
    LIVE_RECOMMENDATION = "live_recommendation"


class DataProviderLevel(StrEnum):
    LEVEL_0_FIXTURE = "LEVEL_0_FIXTURE"
    LEVEL_1_PUBLIC_OFFICIAL = "LEVEL_1_PUBLIC_OFFICIAL"
    LEVEL_2_MARKET_DATA_VENDOR = "LEVEL_2_MARKET_DATA_VENDOR"
    LEVEL_3_BROKER_READ_ONLY = "LEVEL_3_BROKER_READ_ONLY"
    LEVEL_4_PAPER_TRADING = "LEVEL_4_PAPER_TRADING"
    LEVEL_5_LIVE_EXECUTION = "LEVEL_5_LIVE_EXECUTION"


class RecommendationAction(StrEnum):
    BUY = "buy"
    ADD = "add"
    HOLD = "hold"
    TRIM = "trim"
    SELL = "sell"
    AVOID = "avoid"
    WATCH = "watch"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class EvidenceGateResult:
    passed: bool
    score: float
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValuationGateResult:
    passed: bool
    score: float
    valuation_basis: str = ""
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskGateResult:
    passed: bool
    score: float
    risk_warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioGateResult:
    passed: bool
    portfolio_fit_score: float
    current_weight_pct: float = 0.0
    max_position_pct: float = 0.0
    concentration_warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RedTeamResult:
    passed: bool
    strongest_bear_case: str = ""
    missing_evidence: tuple[str, ...] = ()
    thesis_kill_triggers: tuple[str, ...] = ()
    downgrade_triggers: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockPickerScore:
    ticker: str
    company_name: str
    market: str
    rank: int
    score: float
    tier: str
    factor_scores: dict[str, float] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()
    schema_version: str = AUTOPM_SCHEMA_VERSION


@dataclass(frozen=True)
class PortfolioAwareRecommendation:
    ticker: str
    company_name: str
    market: str
    action: RecommendationAction
    rating: str
    conviction_score: float
    current_weight_pct: float
    target_weight_pct: float
    delta_weight_pct: float
    max_position_pct: float
    evidence_score: float
    valuation_score: float
    quality_score: float
    momentum_score: float
    risk_score: float
    portfolio_fit_score: float
    reason_codes: tuple[str, ...] = ()
    risk_warnings: tuple[str, ...] = ()
    thesis_kill_triggers: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()
    not_personal_financial_advice: bool = True
    schema_version: str = AUTOPM_SCHEMA_VERSION


@dataclass(frozen=True)
class PositionSizingDecision:
    ticker: str
    current_weight_pct: float
    target_weight_pct: float
    delta_weight_pct: float
    max_position_pct: float
    reason_codes: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    schema_version: str = AUTOPM_SCHEMA_VERSION


@dataclass(frozen=True)
class RebalanceProposal:
    as_of_date: str
    starting_cash_pct: float
    ending_cash_pct: float
    proposed_trades: tuple[dict[str, object], ...] = ()
    blocked_recommendations: tuple[dict[str, object], ...] = ()
    not_executed: bool = True
    schema_version: str = AUTOPM_SCHEMA_VERSION


@dataclass(frozen=True)
class AutopmRunManifest:
    run_id: str
    mode: AutopmMode = AutopmMode.DISABLED
    schema_version: str = AUTOPM_SCHEMA_VERSION
    provider_levels: tuple[DataProviderLevel, ...] = ()
    source_manifest_path: str = ""
    policy_manifest_path: str = ""
    output_manifest_path: str = ""
    warning_codes: tuple[str, ...] = ()

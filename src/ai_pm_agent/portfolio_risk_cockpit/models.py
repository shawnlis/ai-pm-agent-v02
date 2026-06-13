"""Data models for the offline Portfolio Risk Cockpit."""

from __future__ import annotations

from dataclasses import dataclass, field


SCHEMA_VERSION = "v0.5.0-phase1"

REVIEW_OK = "OK"
NEEDS_REVIEW = "NEEDS_REVIEW"

UNKNOWN_INSTRUMENT_TYPE = "UNKNOWN_INSTRUMENT_TYPE"
SHORT_OPTION_NEEDS_REVIEW = "SHORT_OPTION_NEEDS_REVIEW"
DISALLOWED_REAL_PORTFOLIO_INPUT = "DISALLOWED_REAL_PORTFOLIO_INPUT"

SAFETY_BOUNDARY = {
    "system_type": "portfolio_risk_cockpit",
    "fixture_input_only": True,
    "risk_report_only": True,
    "investment_recommendation": False,
    "client_advice": False,
    "portfolio_csv_used": False,
    "ibkr_content_inspected": False,
    "broker_data_used": False,
    "client_data_used": False,
    "broker_connection": False,
    "trading": False,
    "network_access": False,
    "live_market_data": False,
    "llm": False,
    "pm_prompt_wiring": False,
}


@dataclass(frozen=True)
class PortfolioRiskPosition:
    ticker: str
    instrument_type: str
    quantity: float
    currency: str
    market_value: float
    notional_value: float
    exposure_multiplier: float
    underlying_ticker: str | None = None
    themes: tuple[str, ...] = field(default_factory=tuple)
    region: str = "UNKNOWN"
    notes: str | None = None
    review_status: str = REVIEW_OK
    warning_codes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def gross_market_value(self) -> float:
        return abs(self.market_value)

    @property
    def gross_exposure_value(self) -> float:
        return abs(self.notional_value)

    @property
    def leverage_adjusted_exposure(self) -> float:
        return self.gross_exposure_value * self.exposure_multiplier

    @property
    def is_needs_review(self) -> bool:
        return self.review_status == NEEDS_REVIEW


@dataclass(frozen=True)
class PortfolioRiskCockpitResult:
    as_of_date: str
    input_path: str
    positions: list[PortfolioRiskPosition]
    exposure_by_ticker: list[dict[str, object]]
    exposure_by_theme: list[dict[str, object]]
    exposure_by_currency: list[dict[str, object]]
    exposure_by_region: list[dict[str, object]]
    stress_scenarios: list[dict[str, object]]
    summary: dict[str, object]
    warning_codes: list[str]
    files: dict[str, str] = field(default_factory=dict)

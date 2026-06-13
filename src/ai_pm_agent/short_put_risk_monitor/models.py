"""Data models for the offline Short Put Risk Monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


SCHEMA_VERSION = "v0.5.1-phase1"

REVIEW_OK = "OK"
REVIEW_NEEDS_REVIEW = "NEEDS_REVIEW"

MISSING_EXPIRY = "MISSING_EXPIRY"
EXPIRED_OPTION = "EXPIRED_OPTION"
MISSING_UNDERLYING_PRICE = "MISSING_UNDERLYING_PRICE"
NEAR_STRIKE = "NEAR_STRIKE"
BELOW_STRIKE = "BELOW_STRIKE"
BELOW_BREAKEVEN = "BELOW_BREAKEVEN"
LARGE_ASSIGNMENT_NOTIONAL = "LARGE_ASSIGNMENT_NOTIONAL"
NEEDS_REVIEW = "NEEDS_REVIEW"
DISALLOWED_REAL_SHORT_PUT_INPUT = "DISALLOWED_REAL_SHORT_PUT_INPUT"

SAFETY_BOUNDARY = {
    "system_type": "short_put_risk_monitor",
    "fixture_input_only": True,
    "short_put_risk_report_only": True,
    "options_recommendation": False,
    "investment_recommendation": False,
    "roll_close_open_recommendation": False,
    "broker_connection": False,
    "ibkr_content_inspected": False,
    "trading": False,
    "order_placement": False,
    "network_access": False,
    "live_market_data": False,
    "yfinance": False,
    "web_search": False,
    "llm": False,
    "client_data_used": False,
    "pm_prompt_wiring": False,
}


@dataclass(frozen=True)
class ShortPutPosition:
    option_id: str
    underlying_ticker: str
    expiry_date: date | None
    strike: float
    contracts: float
    contract_multiplier: float
    premium_collected: float
    current_underlying_price: float | None
    currency: str
    underlying_theme: str
    notes: str | None = None
    review_status: str = REVIEW_OK
    warning_codes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def contract_count(self) -> float:
        return abs(self.contracts)

    @property
    def underlying_units(self) -> float:
        return self.contract_count * self.contract_multiplier

    @property
    def gross_notional(self) -> float:
        return self.strike * self.underlying_units

    @property
    def assignment_notional(self) -> float:
        return self.gross_notional

    @property
    def premium_per_unit(self) -> float:
        if self.underlying_units == 0:
            return 0.0
        return self.premium_collected / self.underlying_units

    @property
    def breakeven_price(self) -> float:
        return self.strike - self.premium_per_unit

    @property
    def is_needs_review(self) -> bool:
        return self.review_status == REVIEW_NEEDS_REVIEW


@dataclass(frozen=True)
class ShortPutRiskMonitorResult:
    as_of_date: str
    input_path: str
    positions: list[ShortPutPosition]
    position_rows: list[dict[str, object]]
    stress_rows: list[dict[str, object]]
    summary: dict[str, object]
    warning_codes: list[str]
    files: dict[str, str] = field(default_factory=dict)

"""Input and output contracts for Short Put Risk Monitor v0.5.1."""

from __future__ import annotations


SHORT_PUT_INPUT_FIELDS = [
    "option_id",
    "underlying_ticker",
    "expiry_date",
    "strike",
    "contracts",
    "contract_multiplier",
    "premium_collected",
    "current_underlying_price",
    "currency",
    "underlying_theme",
    "notes",
]

SHORT_PUT_POSITION_FIELDS = [
    "option_id",
    "underlying_ticker",
    "expiry_date",
    "days_to_expiry",
    "strike",
    "contracts",
    "contract_multiplier",
    "premium_collected",
    "current_underlying_price",
    "currency",
    "underlying_theme",
    "gross_notional",
    "assignment_notional",
    "breakeven_price",
    "distance_to_strike_pct",
    "distance_to_breakeven_pct",
    "review_status",
    "warning_codes",
    "notes",
]

SHORT_PUT_STRESS_FIELDS = [
    "option_id",
    "underlying_ticker",
    "scenario",
    "stress_price",
    "stress_price_source",
    "gross_notional",
    "assignment_notional",
    "intrinsic_loss_at_stress",
    "premium_collected",
    "max_simple_downside_at_stress",
    "review_status",
    "warning_codes",
]

REPORT_FILENAME = "SHORT_PUT_RISK_MONITOR_V051.md"
SUMMARY_FILENAME = "short_put_risk_summary.json"
POSITIONS_FILENAME = "short_put_positions.csv"
STRESS_FILENAME = "short_put_stress_scenarios.csv"
WARNINGS_FILENAME = "short_put_warnings.md"

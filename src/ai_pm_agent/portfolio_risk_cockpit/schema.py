"""CSV and output contracts for Portfolio Risk Cockpit v0.5.0 Phase 1."""

from __future__ import annotations


PORTFOLIO_INPUT_FIELDS = [
    "ticker",
    "instrument_type",
    "quantity",
    "currency",
    "market_value",
    "notional_value",
    "exposure_multiplier",
    "underlying_ticker",
    "theme",
    "region",
    "notes",
]

EXPOSURE_BY_TICKER_FIELDS = [
    "ticker",
    "instrument_count",
    "gross_market_value",
    "gross_exposure",
    "leverage_adjusted_exposure",
    "pct_gross_market_value",
    "pct_leverage_adjusted_exposure",
    "review_status",
    "warning_codes",
]

EXPOSURE_BY_BUCKET_FIELDS = [
    "bucket",
    "gross_market_value",
    "gross_exposure",
    "leverage_adjusted_exposure",
    "pct_gross_market_value",
    "pct_leverage_adjusted_exposure",
    "review_status",
    "warning_codes",
]

STRESS_SCENARIO_FIELDS = [
    "scenario",
    "shock_pct",
    "impacted_tickers",
    "impacted_exposure",
    "estimated_impact_value",
    "estimated_impact_pct_of_gross_market_value",
    "notes",
]

REPORT_FILENAME = "PORTFOLIO_RISK_COCKPIT_V050.md"
SUMMARY_FILENAME = "portfolio_risk_summary.json"
TICKER_EXPOSURE_FILENAME = "exposure_by_ticker.csv"
THEME_EXPOSURE_FILENAME = "exposure_by_theme.csv"
CURRENCY_EXPOSURE_FILENAME = "exposure_by_currency.csv"
STRESS_SCENARIOS_FILENAME = "stress_scenarios.csv"
WARNINGS_FILENAME = "risk_warnings.md"

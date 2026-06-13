"""Models and safety constants for Risk Cockpit Pipeline v0.5.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v0.5.2-phase1"

REVIEW_OK = "OK"
REVIEW_NEEDS_REVIEW = "NEEDS_REVIEW"

MISSING_PORTFOLIO_ARTIFACT = "MISSING_PORTFOLIO_ARTIFACT"
MISSING_SHORT_PUT_ARTIFACT = "MISSING_SHORT_PUT_ARTIFACT"
MISSING_MARKET_DATA = "MISSING_MARKET_DATA"
STALE_MARKET_DATA = "STALE_MARKET_DATA"
PRICE_MISMATCH_NEEDS_REVIEW = "PRICE_MISMATCH_NEEDS_REVIEW"
MARKET_DATA_FIXTURE_ONLY = "MARKET_DATA_FIXTURE_ONLY"
MARKET_DATA_NOT_FIXTURE = "MARKET_DATA_NOT_FIXTURE"
RISK_ARTIFACT_NEEDS_REVIEW = "RISK_ARTIFACT_NEEDS_REVIEW"
PIPELINE_REVIEW_REQUIRED = "PIPELINE_REVIEW_REQUIRED"
PIPELINE_FAILED_CLOSED = "PIPELINE_FAILED_CLOSED"
MARKET_DATA_LOAD_FAILED = "MARKET_DATA_LOAD_FAILED"
FOUNDATION_REPORT_FAILED = "FOUNDATION_REPORT_FAILED"
ARTIFACT_READ_FAILED = "ARTIFACT_READ_FAILED"
DISALLOWED_REAL_DATA_PATH = "DISALLOWED_REAL_DATA_PATH"
NO_LIVE_MARKET_DATA = "NO_LIVE_MARKET_DATA"

REVIEW_WARNING_CODES = {
    MISSING_PORTFOLIO_ARTIFACT,
    MISSING_SHORT_PUT_ARTIFACT,
    MISSING_MARKET_DATA,
    STALE_MARKET_DATA,
    PRICE_MISMATCH_NEEDS_REVIEW,
    MARKET_DATA_NOT_FIXTURE,
    RISK_ARTIFACT_NEEDS_REVIEW,
    PIPELINE_REVIEW_REQUIRED,
    PIPELINE_FAILED_CLOSED,
    MARKET_DATA_LOAD_FAILED,
    FOUNDATION_REPORT_FAILED,
    ARTIFACT_READ_FAILED,
    DISALLOWED_REAL_DATA_PATH,
}

SAFETY_BOUNDARY = {
    "risk_report_only": True,
    "investment_recommendation": False,
    "options_recommendation": False,
    "client_advice": False,
    "broker_connection": False,
    "ibkr_content_inspected": False,
    "trading": False,
    "order_placement": False,
    "live_market_data": False,
    "market_data_provider_level": "Level 0",
    "fixture_market_data_only": True,
    "yfinance": False,
    "web_search": False,
    "llm": False,
    "client_data_used": False,
    "pm_prompt_wiring": False,
    "recommendation_output": False,
}


class RiskCockpitPipelineError(ValueError):
    """Raised when Risk Cockpit Pipeline input or execution fails closed."""


class RiskCockpitPipelineFailure(RiskCockpitPipelineError):
    """Raised after a post-start pipeline failure writes an audit index."""

    def __init__(self, message: str, *, index_path: str | None = None) -> None:
        super().__init__(message)
        self.index_path = index_path


@dataclass(frozen=True)
class MarketDataPoint:
    ticker: str
    price: float
    currency: str
    as_of_date: str
    source: str
    source_confidence: str
    fixture_only: bool
    notes: str = ""


@dataclass(frozen=True)
class MarketDataProviderSnapshot:
    provider_name: str
    provider_level: str
    network_access: bool
    live_market_data: bool
    fixture_only: bool
    points: list[MarketDataPoint]
    warning_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactReadResult:
    artifact_rows: list[dict[str, object]]
    warning_codes: list[str]
    portfolio_ticker_rows: list[dict[str, str]] = field(default_factory=list)
    short_put_position_rows: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RiskCockpitPipelineResult:
    run_id: str
    generated_at: str
    as_of_date: str
    output_dir: str
    portfolio_report_dir: str
    short_put_report_dir: str
    portfolio_input_path: str
    short_put_input_path: str
    market_data_fixture_path: str
    index: dict[str, Any]
    artifact_rows: list[dict[str, object]]
    warning_rows: list[dict[str, object]]
    market_data_rows: list[dict[str, object]]
    enrichment_rows: list[dict[str, object]]
    warning_codes: list[str]
    review_required: bool
    files: dict[str, str] = field(default_factory=dict)


def assert_safe_input_path(path: str | Path) -> Path:
    """Reject real-data-looking paths before existence or content reads."""

    candidate = Path(path)
    text = str(candidate).lower()
    basename = candidate.name.lower()
    parts = [part.lower() for part in candidate.parts]
    disallowed = (
        basename == "portfolio.csv"
        or any("ibkr positions" in part for part in parts)
        or any(marker in text for marker in ("ibkr", "broker", "client"))
    )
    if disallowed:
        raise RiskCockpitPipelineError(
            f"{DISALLOWED_REAL_DATA_PATH}: Risk Cockpit Pipeline v0.5.2 accepts fixture/report inputs only "
            "and refuses real portfolio/broker/client-looking paths before reading file contents."
        )
    return candidate


def unique_codes(codes: list[str]) -> list[str]:
    return sorted(dict.fromkeys(code for code in codes if code))


def requires_review(codes: list[str]) -> bool:
    return any(code in REVIEW_WARNING_CODES for code in codes)

"""Models for AI infrastructure opportunity discovery v0.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v0.1"

STATUSES = [
    "OPPORTUNITY_REVIEW",
    "THESIS_IMPROVING",
    "CATALYST_MONITOR",
    "VALUATION_BLOCKED",
    "EVIDENCE_BLOCKED",
    "RISK_BLOCKED",
    "WATCHLIST_ONLY",
    "DO_NOT_USE",
]

STATUS_RANK = {status: index for index, status in enumerate(STATUSES)}

SAFETY_FLAGS = {
    "investment_recommendation": False,
    "recommendation_engine": False,
    "pm_prompt_wiring": False,
    "portfolio_data_used": False,
    "broker_data_used": False,
    "client_data_used": False,
    "trading": False,
    "order_placement": False,
    "network_access": False,
    "live_sec_fetch": False,
    "web_search": False,
    "llm": False,
    "yfinance": False,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


@dataclass(frozen=True)
class DiscoveryInputPaths:
    evidence_dir: Path
    monitor_dir: Path
    ledger_csv: Path
    metric_history_csv: Path
    source_manifest_json: Path
    thesis_gap_table_csv: Path
    thesis_gap_summary_json: Path
    source_coverage_csv: Path
    monitor_warnings_md: Path
    prior_monitor_dir: Path | None = None


@dataclass(frozen=True)
class DiscoveryInputBundle:
    paths: DiscoveryInputPaths
    ledger_rows: list[dict[str, str]]
    metric_rows: list[dict[str, str]]
    source_manifest: dict[str, Any]
    thesis_gap_rows: list[dict[str, str]]
    thesis_gap_summary: dict[str, Any]
    source_coverage_rows: list[dict[str, str]]
    monitor_warnings_text: str


@dataclass(frozen=True)
class OpportunityCandidate:
    company: str
    company_name: str
    status: str
    total_score: int
    evidence_strength_score: int
    gap_closure_score: int
    source_freshness_score: int
    catalyst_signal_score: int
    valuation_data_availability_score: int
    risk_blocker_penalty: int
    missing_data_penalty: int
    improving_gap_count: int
    closed_gap_count: int
    partially_closed_gap_count: int
    source_count: int
    newest_source_date: str
    valuation_data_available: bool
    source_coverage_status: str
    warning_codes: tuple[str, ...] = field(default_factory=tuple)
    review_note: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "company_name": self.company_name,
            "status": self.status,
            "total_score": self.total_score,
            "evidence_strength_score": self.evidence_strength_score,
            "gap_closure_score": self.gap_closure_score,
            "source_freshness_score": self.source_freshness_score,
            "catalyst_signal_score": self.catalyst_signal_score,
            "valuation_data_availability_score": self.valuation_data_availability_score,
            "risk_blocker_penalty": self.risk_blocker_penalty,
            "missing_data_penalty": self.missing_data_penalty,
            "improving_gap_count": self.improving_gap_count,
            "closed_gap_count": self.closed_gap_count,
            "partially_closed_gap_count": self.partially_closed_gap_count,
            "source_count": self.source_count,
            "newest_source_date": self.newest_source_date,
            "valuation_data_available": str(self.valuation_data_available).lower(),
            "source_coverage_status": self.source_coverage_status,
            "warning_codes": ";".join(self.warning_codes),
            "review_note": self.review_note,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[OpportunityCandidate]
    status_counts: dict[str, int]
    warning_codes: tuple[str, ...]
    input_paths: DiscoveryInputPaths
    generated_at: str = field(default_factory=utc_now)

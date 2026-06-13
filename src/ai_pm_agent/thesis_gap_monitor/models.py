"""Data models for the AI infrastructure thesis-gap monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
from typing import Any


DEFAULT_COMPANIES = ["MU", "NVDA", "AMD", "AVGO", "MSFT", "GOOGL"]

GAP_STATUSES = [
    "CLOSED",
    "PARTIALLY_CLOSED",
    "UNCHANGED",
    "WORSENED",
    "UNKNOWN",
    "NEEDS_REVIEW",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def stable_gap_id(company: str, theme_id: str) -> str:
    material = f"{company.strip().upper()}|{theme_id.strip().lower()}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"gap_{digest}"


@dataclass(frozen=True)
class ThemeDefinition:
    theme_id: str
    theme: str
    gap_question: str
    why_it_matters: str
    what_would_close_the_gap: str
    keywords: tuple[str, ...]
    risk_keywords: tuple[str, ...] = ()


THEMES = [
    ThemeDefinition(
        theme_id="ai_capex",
        theme="AI capex",
        gap_question="Is AI infrastructure capex supported by source-backed monetization evidence?",
        why_it_matters="Capex growth without monetization evidence can create ROI and margin risk.",
        what_would_close_the_gap="Company filing or official IR evidence tying AI capex to material revenue, contracted demand, or disclosed returns.",
        keywords=("ai", "capex", "capital expenditure", "property and equipment", "data center", "infrastructure"),
        risk_keywords=("capex burden", "roi risk", "margin pressure", "without revenue", "monetization"),
    ),
    ThemeDefinition(
        theme_id="hbm_memory",
        theme="HBM / memory",
        gap_question="Is HBM or memory demand supported by official source evidence beyond samples or qualification?",
        why_it_matters="Sample or qualification evidence does not prove volume production or material revenue.",
        what_would_close_the_gap="Official evidence of volume production plus material revenue contribution or contracted demand.",
        keywords=("hbm", "memory", "dram", "nand", "wafer", "inventory"),
        risk_keywords=("oversupply", "constraint", "shortage", "slowdown", "inventory correction"),
    ),
    ThemeDefinition(
        theme_id="gpu_accelerator_demand",
        theme="GPU / accelerator demand",
        gap_question="Is GPU or accelerator demand visible in official company evidence?",
        why_it_matters="Demand claims require source-backed evidence rather than broad AI market narratives.",
        what_would_close_the_gap="Official evidence of accelerator shipments, revenue, backlog, or durable customer demand.",
        keywords=("gpu", "accelerator", "graphics", "compute", "cuda", "data center"),
        risk_keywords=("slowdown", "constraint", "delay", "excess inventory"),
    ),
    ThemeDefinition(
        theme_id="networking_asic_custom_silicon",
        theme="networking / ASIC / custom silicon",
        gap_question="Is networking, ASIC, or custom silicon demand source-backed?",
        why_it_matters="Custom silicon claims need evidence of production, customer adoption, and monetization.",
        what_would_close_the_gap="Official evidence of custom silicon revenue, customer commitments, or volume production.",
        keywords=("networking", "ethernet", "switch", "asic", "custom silicon", "custom accelerator", "tpu"),
        risk_keywords=("customer concentration", "qualification", "sampling", "delay"),
    ),
    ThemeDefinition(
        theme_id="cloud_infrastructure",
        theme="cloud infrastructure",
        gap_question="Is cloud infrastructure growth supported by disclosed operating or revenue evidence?",
        why_it_matters="Cloud infrastructure buildout can create margin pressure if demand monetization lags.",
        what_would_close_the_gap="Official evidence of cloud revenue growth, contracted demand, utilization, or margin stability.",
        keywords=("cloud", "azure", "google cloud", "server", "infrastructure", "data center"),
        risk_keywords=("margin pressure", "capacity", "capex burden", "slowdown"),
    ),
    ThemeDefinition(
        theme_id="data_center_margin_capex_burden",
        theme="data center margin / capex burden",
        gap_question="Does data center growth improve economics, or does capex burden remain unresolved?",
        why_it_matters="AI demand can still be value-destructive if infrastructure costs outrun monetization.",
        what_would_close_the_gap="Official evidence of data center margin expansion, return on capex, or revenue conversion.",
        keywords=("data center", "capex", "capital expenditure", "margin", "gross profit", "operating income"),
        risk_keywords=("margin pressure", "capex burden", "roi risk", "depreciation", "without revenue"),
    ),
    ThemeDefinition(
        theme_id="supply_constraint_vs_demand_slowdown",
        theme="supply constraint vs demand slowdown",
        gap_question="Does evidence point to supply constraints, demand slowdown, or unresolved uncertainty?",
        why_it_matters="Supply-constrained demand and slowing demand imply different thesis risks.",
        what_would_close_the_gap="Official evidence distinguishing supply limits from demand softness with disclosed orders, backlog, or inventory trends.",
        keywords=("supply", "constraint", "demand", "slowdown", "inventory", "backlog", "capacity"),
        risk_keywords=("slowdown", "inventory correction", "cancellation", "oversupply", "softness"),
    ),
    ThemeDefinition(
        theme_id="customer_concentration",
        theme="customer concentration",
        gap_question="Is customer concentration disclosed or still an unresolved risk?",
        why_it_matters="AI infrastructure revenue can be fragile if concentrated in a few customers.",
        what_would_close_the_gap="Official customer concentration disclosure with manageable exposure or diversified demand evidence.",
        keywords=("customer", "concentration", "major customer", "accounts receivable", "counterparty"),
        risk_keywords=("major customer", "concentration", "single customer", "two customers"),
    ),
    ThemeDefinition(
        theme_id="revenue_recognition_backlog_deferred_revenue",
        theme="revenue recognition / backlog / deferred revenue",
        gap_question="Does backlog, deferred revenue, or revenue recognition evidence support future AI infrastructure revenue?",
        why_it_matters="Backlog and deferred revenue can support visibility, but must be source-backed and not double-counted.",
        what_would_close_the_gap="Official evidence of backlog, remaining performance obligations, deferred revenue conversion, or recognized revenue.",
        keywords=("revenue", "backlog", "deferred revenue", "remaining performance obligation", "rpo", "contract liability"),
        risk_keywords=("recognition risk", "cancellation", "deferral", "collectability"),
    ),
]


@dataclass(frozen=True)
class EvidenceInputPaths:
    ledger_csv: Path
    metric_history_csv: Path
    source_manifest_json: Path
    warnings_md: Path | None = None
    evidence_db_sqlite: Path | None = None


@dataclass(frozen=True)
class EvidenceBundle:
    input_paths: EvidenceInputPaths
    ledger_rows: list[dict[str, str]]
    metric_rows: list[dict[str, str]]
    manifest: dict[str, Any]
    warnings_text: str = ""


@dataclass(frozen=True)
class ThesisGap:
    company: str
    theme: str
    gap_id: str
    gap_question: str
    current_status: str
    evidence_summary: str
    source_count: int
    newest_source_date: str
    confidence: str
    warning_codes: tuple[str, ...]
    human_review_required: bool
    why_it_matters: str
    what_would_close_the_gap: str

    def as_row(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "theme": self.theme,
            "gap_id": self.gap_id,
            "gap_question": self.gap_question,
            "current_status": self.current_status,
            "evidence_summary": self.evidence_summary,
            "source_count": self.source_count,
            "newest_source_date": self.newest_source_date,
            "confidence": self.confidence,
            "warning_codes": ";".join(self.warning_codes),
            "human_review_required": str(self.human_review_required).lower(),
            "why_it_matters": self.why_it_matters,
            "what_would_close_the_gap": self.what_would_close_the_gap,
        }


@dataclass(frozen=True)
class SourceCoverage:
    company: str
    company_name: str
    evidence_rows: int
    metric_rows: int
    source_count: int
    newest_source_date: str
    warning_codes: tuple[str, ...]
    coverage_status: str

    def as_row(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "company_name": self.company_name,
            "evidence_rows": self.evidence_rows,
            "metric_rows": self.metric_rows,
            "source_count": self.source_count,
            "newest_source_date": self.newest_source_date,
            "warning_codes": ";".join(self.warning_codes),
            "coverage_status": self.coverage_status,
        }


@dataclass(frozen=True)
class MonitorResult:
    gaps: list[ThesisGap]
    coverage: list[SourceCoverage]
    status_counts: dict[str, int]
    warning_codes: tuple[str, ...]
    manifest_summary: dict[str, Any]
    generated_at: str = field(default_factory=utc_now)

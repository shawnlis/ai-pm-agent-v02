"""Offline watchlist and data-quality report generation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.reports.markdown import bullet_list, generated_at, rows_to_dicts, section, table


@dataclass(frozen=True)
class ReportOutput:
    markdown: str
    csv_rows: list[dict[str, Any]]
    csv_fields: list[str]


LATEST_FIELDS = [
    "ticker",
    "company_name",
    "market",
    "action",
    "rating",
    "pm_score",
    "chokepoint_score",
    "confidence",
    "latest_run_date",
    "warning_count",
]

TOP_CHOKEPOINT_FIELDS = [
    "ticker",
    "company_name",
    "market",
    "chokepoint_score",
    "evidence_level",
    "action",
    "rating",
    "pm_score",
    "confidence",
    "latest_run_date",
    "warning_count",
]

STALE_FIELDS = [
    "ticker",
    "company_name",
    "market",
    "latest_run_date",
    "missing_artifacts",
    "warning_count",
    "evidence_count",
    "facts_count",
    "has_market_snapshot",
    "has_pm_decision",
    "has_chokepoint_assessment",
]

WARNING_FIELDS = [
    "warning_type",
    "ticker",
    "company_name",
    "latest_run_date",
    "message",
    "artifact_path",
]

DECISION_CHANGE_FIELDS = [
    "ticker",
    "company_name",
    "market",
    "previous_run_date",
    "latest_run_date",
    "previous_action",
    "action",
    "previous_rating",
    "rating",
    "previous_pm_score",
    "pm_score",
    "pm_score_change",
    "previous_chokepoint_score",
    "chokepoint_score",
    "chokepoint_score_change",
    "artifact_dir",
]


class WatchlistReportGenerator:
    """Build deterministic Markdown watchlist and data-quality reports."""

    def __init__(self, repo: CompanyResearchRepository):
        self.repo = repo

    def top_chokepoints(self, limit: int = 25) -> ReportOutput:
        rows = self.repo.filter_decisions(limit=limit, sort="chokepoint_score", desc=True)
        dicts = rows_to_dicts(rows)
        summary = self.repo.summarize_database()
        markdown = self._header("Top Chokepoint Report") + "\n\n"
        markdown += bullet_list(
            [
                f"Generated: {generated_at()}",
                f"DB path: `{self.repo.db_path}`",
                f"Companies considered: {summary['counts']['companies']}",
                f"Rows displayed: {len(dicts)}",
            ]
        )
        markdown += "\n\n" + table(TOP_CHOKEPOINT_FIELDS, _select(dicts, TOP_CHOKEPOINT_FIELDS))
        markdown += "\n\n" + section("Rule-Based Observations", self._observations(dicts))
        return ReportOutput(markdown=markdown, csv_rows=dicts, csv_fields=TOP_CHOKEPOINT_FIELDS)

    def latest_decisions(self, limit: int = 50) -> ReportOutput:
        rows = self.repo.filter_decisions(limit=limit, sort="latest_run_date", desc=True)
        dicts = rows_to_dicts(rows)
        action_counts = Counter(row.get("action") or "N/A" for row in dicts)
        rating_counts = Counter(row.get("rating") or "N/A" for row in dicts)
        markdown = self._header("Latest Decisions Report") + "\n\n"
        markdown += bullet_list(
            [
                f"Generated: {generated_at()}",
                f"DB path: `{self.repo.db_path}`",
                f"Rows displayed: {len(dicts)}",
                "Action counts: " + _counter_text(action_counts),
                "Rating counts: " + _counter_text(rating_counts),
            ]
        )
        markdown += "\n\n" + table(LATEST_FIELDS, _select(dicts, LATEST_FIELDS))
        return ReportOutput(markdown=markdown, csv_rows=dicts, csv_fields=LATEST_FIELDS)

    def stale(self, limit: int = 200) -> ReportOutput:
        rows = self.repo.list_stale_or_incomplete_companies(limit=limit)
        dicts = rows_to_dicts(rows)
        markdown = self._header("Stale / Incomplete Company Data Report") + "\n\n"
        markdown += bullet_list(
            [
                f"Generated: {generated_at()}",
                f"DB path: `{self.repo.db_path}`",
                f"Rows displayed: {len(dicts)}",
                "This report flags warning-bearing rows, missing evidence/facts, and missing core parsed tables.",
            ]
        )
        markdown += "\n\n" + table(STALE_FIELDS, _select(dicts, STALE_FIELDS))
        return ReportOutput(markdown=markdown, csv_rows=dicts, csv_fields=STALE_FIELDS)

    def warnings(self, limit: int = 500) -> ReportOutput:
        rows = self.repo.list_import_warnings(limit=limit)
        dicts = rows_to_dicts(rows)
        type_counts = self.repo.summarize_database()["warning_types"]
        markdown = self._header("Import Warning Summary Report") + "\n\n"
        markdown += bullet_list(
            [
                f"Generated: {generated_at()}",
                f"DB path: `{self.repo.db_path}`",
                f"Rows displayed: {len(dicts)}",
                "Warning counts: " + _counter_text(type_counts),
            ]
        )
        markdown += "\n\n" + table(WARNING_FIELDS, _select(dicts, WARNING_FIELDS))
        return ReportOutput(markdown=markdown, csv_rows=dicts, csv_fields=WARNING_FIELDS)

    def decision_changes(self, limit: int = 200) -> ReportOutput:
        rows = self.repo.list_decision_changes(limit=limit)
        dicts = rows_to_dicts(rows)
        markdown = self._header("Decision Change Report") + "\n\n"
        markdown += bullet_list(
            [
                f"Generated: {generated_at()}",
                f"DB path: `{self.repo.db_path}`",
                f"Rows displayed: {len(dicts)}",
                "Rows represent tickers with more than one run and a changed action, rating, PM score, or chokepoint score.",
            ]
        )
        markdown += "\n\n" + table(DECISION_CHANGE_FIELDS, _select(dicts, DECISION_CHANGE_FIELDS))
        return ReportOutput(markdown=markdown, csv_rows=dicts, csv_fields=DECISION_CHANGE_FIELDS)

    def _observations(self, rows: list[dict[str, Any]]) -> str:
        observations: list[str] = []
        top = [row for row in rows if _num(row.get("chokepoint_score")) is not None][:5]
        if top:
            observations.append(
                "Highest chokepoint scores: "
                + ", ".join(f"{row.get('ticker')} ({row.get('chokepoint_score')})" for row in top[:5])
            )
        high_ch_low_pm = [
            row
            for row in rows
            if (_num(row.get("chokepoint_score")) or -999) >= 8
            and (_num(row.get("pm_score")) is None or (_num(row.get("pm_score")) or 0) < 5)
        ]
        if high_ch_low_pm:
            observations.append(
                "High chokepoint but low/missing PM score: "
                + ", ".join(row.get("ticker") or "N/A" for row in high_ch_low_pm[:10])
            )
        high_warning = [row for row in rows if int(row.get("warning_count") or 0) >= 5]
        if high_warning:
            observations.append(
                "High warning count: " + ", ".join(row.get("ticker") or "N/A" for row in high_warning[:10])
            )
        missing_evidence = [row for row in rows if int(row.get("evidence_count") or 0) == 0]
        if missing_evidence:
            observations.append(
                "Missing evidence rows: "
                + ", ".join(row.get("ticker") or "N/A" for row in missing_evidence[:10])
            )
        missing_facts = [row for row in rows if int(row.get("facts_count") or 0) == 0]
        if missing_facts:
            observations.append(
                "Missing fact rows: " + ", ".join(row.get("ticker") or "N/A" for row in missing_facts[:10])
            )
        stale_rows = self.repo.list_stale_or_incomplete_companies(limit=10)
        if stale_rows:
            observations.append(f"Stale/incomplete rows currently flagged: at least {len(stale_rows)}")
        if not observations:
            observations.append("No automatic watchlist observations from the displayed rows.")
        return bullet_list(observations)

    def _header(self, title: str) -> str:
        return f"# {title}"


def _select(rows: list[dict[str, Any]], fields: list[str]) -> list[list[Any]]:
    return [[row.get(field) for field in fields] for row in rows]


def _counter_text(counter: Counter[str]) -> str:
    if not counter:
        return "N/A"
    return ", ".join(f"{key}: {value}" for key, value in sorted(counter.items()))


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

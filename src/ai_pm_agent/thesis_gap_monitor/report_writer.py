"""Output writers for the thesis-gap monitor."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import GAP_STATUSES, MonitorResult, ThesisGap, today_yyyymmdd


REPORT_FILENAME = "AI_INFRA_THESIS_GAP_MONITOR_V2.md"
GAP_TABLE_FILENAME = "thesis_gap_table.csv"
SUMMARY_FILENAME = "thesis_gap_summary.json"
COVERAGE_FILENAME = "source_coverage.csv"
WARNINGS_FILENAME = "monitor_warnings.md"

GAP_FIELDS = [
    "company",
    "theme",
    "gap_id",
    "gap_question",
    "current_status",
    "evidence_summary",
    "source_count",
    "newest_source_date",
    "confidence",
    "warning_codes",
    "human_review_required",
    "why_it_matters",
    "what_would_close_the_gap",
]

COVERAGE_FIELDS = [
    "company",
    "company_name",
    "evidence_rows",
    "metric_rows",
    "source_count",
    "newest_source_date",
    "warning_codes",
    "coverage_status",
]


def default_output_dir() -> Path:
    return Path("reports") / "ai_infra_thesis_gap_monitor" / "v2" / today_yyyymmdd()


def write_outputs(result: MonitorResult, out_dir: Path | str | None = None) -> dict[str, str]:
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    target.mkdir(parents=True, exist_ok=True)

    gap_csv = target / GAP_TABLE_FILENAME
    coverage_csv = target / COVERAGE_FILENAME
    summary_json = target / SUMMARY_FILENAME
    warnings_md = target / WARNINGS_FILENAME
    report_md = target / REPORT_FILENAME

    _write_csv(gap_csv, GAP_FIELDS, [gap.as_row() for gap in result.gaps])
    _write_csv(coverage_csv, COVERAGE_FIELDS, [coverage.as_row() for coverage in result.coverage])
    summary_json.write_text(json.dumps(_summary_payload(result, target), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_md.write_text(_warnings_markdown(result), encoding="utf-8")
    report_md.write_text(_report_markdown(result), encoding="utf-8")

    return {
        "report": str(report_md),
        "thesis_gap_table": str(gap_csv),
        "thesis_gap_summary": str(summary_json),
        "source_coverage": str(coverage_csv),
        "monitor_warnings": str(warnings_md),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _summary_payload(result: MonitorResult, out_dir: Path) -> dict[str, Any]:
    return {
        "generated_at": result.generated_at,
        "output_dir": str(out_dir),
        "boundary": {
            "system_type": "thesis_gap_monitor",
            "investment_recommendation": False,
            "network_access": False,
            "live_sec_fetch": False,
            "uses_existing_evidence_outputs": True,
        },
        "status_counts": result.status_counts,
        "warning_codes": list(result.warning_codes),
        "manifest_summary": result.manifest_summary,
        "companies": sorted({gap.company for gap in result.gaps}),
        "themes": sorted({gap.theme for gap in result.gaps}),
        "gaps": [gap.as_row() for gap in result.gaps],
        "coverage": [coverage.as_row() for coverage in result.coverage],
    }


def _report_markdown(result: MonitorResult) -> str:
    lines = [
        "# AI Infrastructure Thesis-Gap Monitor v2",
        "",
        "This is a thesis-gap monitor, not an investment recommendation.",
        "",
        "## Executive Verdict",
        "",
        _executive_verdict(result),
        "",
        "## Company-by-Company Thesis Gap Table",
        "",
        _gap_table(result.gaps, group_by="company"),
        "",
        "## Theme-by-Theme Gap Table",
        "",
        _theme_table(result.gaps),
        "",
        "## Evidence Coverage Summary",
        "",
        _coverage_table(result),
        "",
        "## Freshness / Staleness Warnings",
        "",
        _freshness_lines(result),
        "",
        "## Status Counts",
        "",
    ]
    for status in GAP_STATUSES:
        lines.append(f"- {status}: {result.status_counts.get(status, 0)}")
    lines.extend(
        [
            "",
            "## Human Review Checklist",
            "",
            "- Review every `UNKNOWN`, `NEEDS_REVIEW`, and `WORSENED` gap before using the output in any memo.",
            "- Confirm that sample evidence is not treated as qualification.",
            "- Confirm that qualification evidence is not treated as volume production.",
            "- Confirm that volume production evidence is not treated as material revenue unless revenue evidence is disclosed.",
            "- Confirm that capex growth without monetization evidence is treated as ROI or margin risk.",
            "- Keep evidence packs separate from PM prompts unless a separately reviewed interface is approved.",
            "",
        ]
    )
    return "\n".join(lines)


def _executive_verdict(result: MonitorResult) -> str:
    counts = result.status_counts
    risk_count = counts.get("WORSENED", 0) + counts.get("NEEDS_REVIEW", 0) + counts.get("UNKNOWN", 0)
    closed_count = counts.get("CLOSED", 0) + counts.get("PARTIALLY_CLOSED", 0)
    return (
        f"The monitor found {closed_count} closed or partially closed gaps and {risk_count} gaps requiring "
        "review, unknown treatment, or risk attention. Outputs are source-backed and conservative; they do "
        "not produce buy, sell, hold, sizing, or rebalance instructions."
    )


def _gap_table(gaps: list[ThesisGap], *, group_by: str) -> str:
    ordered = sorted(gaps, key=lambda gap: (getattr(gap, group_by), gap.theme, gap.company))
    rows = ["| Company | Theme | Status | Confidence | Sources | Human Review |", "|---|---|---|---|---:|---|"]
    for gap in ordered:
        rows.append(
            "| {company} | {theme} | {status} | {confidence} | {sources} | {review} |".format(
                company=gap.company,
                theme=gap.theme,
                status=gap.current_status,
                confidence=gap.confidence,
                sources=gap.source_count,
                review="yes" if gap.human_review_required else "no",
            )
        )
    return "\n".join(rows)


def _theme_table(gaps: list[ThesisGap]) -> str:
    themes = sorted({gap.theme for gap in gaps})
    rows = ["| Theme | CLOSED | PARTIALLY_CLOSED | UNCHANGED | WORSENED | UNKNOWN | NEEDS_REVIEW |", "|---|---:|---:|---:|---:|---:|---:|"]
    for theme in themes:
        theme_gaps = [gap for gap in gaps if gap.theme == theme]
        counts = {status: 0 for status in GAP_STATUSES}
        for gap in theme_gaps:
            counts[gap.current_status] += 1
        rows.append(
            "| {theme} | {closed} | {partial} | {unchanged} | {worsened} | {unknown} | {needs} |".format(
                theme=theme,
                closed=counts["CLOSED"],
                partial=counts["PARTIALLY_CLOSED"],
                unchanged=counts["UNCHANGED"],
                worsened=counts["WORSENED"],
                unknown=counts["UNKNOWN"],
                needs=counts["NEEDS_REVIEW"],
            )
        )
    return "\n".join(rows)


def _coverage_table(result: MonitorResult) -> str:
    rows = ["| Company | Evidence Rows | Metric Rows | Sources | Newest Source Date | Coverage |", "|---|---:|---:|---:|---|---|"]
    for coverage in result.coverage:
        rows.append(
            "| {company} | {evidence} | {metrics} | {sources} | {date} | {status} |".format(
                company=coverage.company,
                evidence=coverage.evidence_rows,
                metrics=coverage.metric_rows,
                sources=coverage.source_count,
                date=coverage.newest_source_date or "UNKNOWN",
                status=coverage.coverage_status,
            )
        )
    return "\n".join(rows)


def _freshness_lines(result: MonitorResult) -> str:
    stale = [coverage for coverage in result.coverage if coverage.coverage_status == "STALE"]
    missing = [coverage for coverage in result.coverage if coverage.coverage_status == "NO_COMPANY_EVIDENCE"]
    if not stale and not missing:
        return "- No stale or missing company-level evidence coverage was detected."
    lines = []
    for coverage in stale:
        lines.append(f"- {coverage.company}: stale evidence; newest source date `{coverage.newest_source_date}`.")
    for coverage in missing:
        lines.append(f"- {coverage.company}: no company evidence rows were available.")
    return "\n".join(lines)


def _warnings_markdown(result: MonitorResult) -> str:
    lines = [
        "# AI Infrastructure Thesis-Gap Monitor v2 Warnings",
        "",
        "This monitor uses existing evidence outputs only. It does not perform live source fetches.",
        "",
    ]
    if not result.warning_codes:
        lines.append("- No monitor warnings.")
    else:
        for code in result.warning_codes:
            lines.append(f"- `{code}`")
    lines.extend(
        [
            "",
            "Boundary:",
            "",
            "- This is a thesis-gap monitor, not an investment recommendation.",
            "- Missing data remains `UNKNOWN`, `NOT_DISCLOSED`, or `NEEDS_REVIEW`.",
            "- Metrics are never fabricated.",
            "",
        ]
    )
    return "\n".join(lines)

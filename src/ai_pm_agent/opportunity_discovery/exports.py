"""Output writers for AI infrastructure opportunity discovery."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import DiscoveryResult, SAFETY_FLAGS, SCHEMA_VERSION, STATUSES, today_yyyymmdd


REPORT_FILENAME = "AI_INFRA_OPPORTUNITY_REVIEW_QUEUE.md"
CANDIDATES_FILENAME = "opportunity_candidates.csv"
SCORECARD_FILENAME = "opportunity_scorecard.json"
WARNINGS_FILENAME = "opportunity_warnings.md"
MANIFEST_FILENAME = "opportunity_discovery_manifest.json"
DELTA_SUMMARY_FILENAME = "opportunity_delta_summary.csv"
TRANSITION_REPORT_FILENAME = "opportunity_transition_report.md"

CANDIDATE_FIELDS = [
    "company",
    "company_name",
    "status",
    "total_score",
    "evidence_strength_score",
    "gap_closure_score",
    "source_freshness_score",
    "catalyst_signal_score",
    "valuation_data_availability_score",
    "risk_blocker_penalty",
    "missing_data_penalty",
    "improving_gap_count",
    "fully_resolved_gap_count",
    "partially_resolved_gap_count",
    "source_count",
    "newest_source_date",
    "valuation_data_available",
    "source_coverage_status",
    "prior_status",
    "current_status",
    "status_change",
    "score_delta",
    "newly_promoted",
    "newly_downgraded",
    "unchanged",
    "why_this_status",
    "what_would_upgrade",
    "what_would_downgrade",
    "unresolved_blockers",
    "required_next_evidence",
    "not_investment_advice",
    "warning_codes",
    "review_note",
]

DELTA_FIELDS = [
    "company",
    "company_name",
    "prior_status",
    "current_status",
    "status_change",
    "score_delta",
    "newly_promoted",
    "newly_downgraded",
    "unchanged",
]


def default_output_dir() -> Path:
    return Path("reports") / "ai_infra_opportunity_discovery" / today_yyyymmdd()


def write_outputs(result: DiscoveryResult, out_dir: Path | str | None = None) -> dict[str, str]:
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    target.mkdir(parents=True, exist_ok=True)

    report_md = target / REPORT_FILENAME
    candidates_csv = target / CANDIDATES_FILENAME
    scorecard_json = target / SCORECARD_FILENAME
    warnings_md = target / WARNINGS_FILENAME
    manifest_json = target / MANIFEST_FILENAME
    delta_csv = target / DELTA_SUMMARY_FILENAME
    transition_md = target / TRANSITION_REPORT_FILENAME

    _write_csv(candidates_csv, CANDIDATE_FIELDS, [candidate.as_row() for candidate in result.candidates])
    _write_csv(delta_csv, DELTA_FIELDS, [_delta_row(candidate.as_row()) for candidate in result.candidates])
    scorecard_json.write_text(json.dumps(_scorecard_payload(result, target), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_md.write_text(_warnings_markdown(result), encoding="utf-8")
    manifest_json.write_text(json.dumps(_manifest_payload(result, target), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md.write_text(_report_markdown(result), encoding="utf-8")
    transition_md.write_text(_transition_markdown(result), encoding="utf-8")

    return {
        "review_queue": str(report_md),
        "opportunity_candidates": str(candidates_csv),
        "opportunity_scorecard": str(scorecard_json),
        "opportunity_warnings": str(warnings_md),
        "opportunity_discovery_manifest": str(manifest_json),
        "opportunity_delta_summary": str(delta_csv),
        "opportunity_transition_report": str(transition_md),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _scorecard_payload(result: DiscoveryResult, out_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": result.generated_at,
        "output_dir": str(out_dir),
        "safety": SAFETY_FLAGS,
        "status_counts": result.status_counts,
        "warning_codes": list(result.warning_codes),
        "candidates": [candidate.as_row() for candidate in result.candidates],
    }


def _manifest_payload(result: DiscoveryResult, out_dir: Path) -> dict[str, Any]:
    paths = result.input_paths
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": result.generated_at,
        "output_dir": str(out_dir),
        "input_paths": {
            "evidence_dir": str(paths.evidence_dir),
            "monitor_dir": str(paths.monitor_dir),
            "company_evidence_ledger": str(paths.ledger_csv),
            "metric_history": str(paths.metric_history_csv),
            "source_manifest": str(paths.source_manifest_json),
            "thesis_gap_table": str(paths.thesis_gap_table_csv),
            "thesis_gap_summary": str(paths.thesis_gap_summary_json),
            "source_coverage": str(paths.source_coverage_csv),
            "monitor_warnings": str(paths.monitor_warnings_md),
            "prior_monitor_dir": str(paths.prior_monitor_dir or ""),
            "prior_scorecard": str(paths.prior_scorecard_json or ""),
            "prior_candidates": str(paths.prior_candidates_csv or ""),
            "risk_summary": str(paths.risk_summary_path or ""),
        },
        "prior_run_used": bool(paths.prior_scorecard_json or paths.prior_candidates_csv),
        "risk_summary_used": bool(paths.risk_summary_path),
        "safety": SAFETY_FLAGS,
        "status_counts": result.status_counts,
        "files_created": [
            str(out_dir / REPORT_FILENAME),
            str(out_dir / CANDIDATES_FILENAME),
            str(out_dir / SCORECARD_FILENAME),
            str(out_dir / WARNINGS_FILENAME),
            str(out_dir / MANIFEST_FILENAME),
            str(out_dir / DELTA_SUMMARY_FILENAME),
            str(out_dir / TRANSITION_REPORT_FILENAME),
        ],
    }


def _report_markdown(result: DiscoveryResult) -> str:
    lines = [
        "# AI Infrastructure Opportunity Review Queue v0.1",
        "",
        "This is a deterministic review queue for AI infrastructure evidence. It is not investment advice.",
        "",
        "## Summary",
        "",
    ]
    for status in STATUSES:
        lines.append(f"- {status}: {result.status_counts.get(status, 0)}")
    lines.extend(
        [
            "",
            "## Queue",
            "",
            "| Company | Status | Score | Improving Gaps | Sources | Valuation Data | Note |",
            "|---|---|---:|---:|---:|---|---|",
        ]
    )
    for candidate in result.candidates:
        lines.append(
            "| {company} | {status} | {score} | {gaps} | {sources} | {valuation} | {note} |".format(
                company=candidate.company,
                status=candidate.status,
                score=candidate.total_score,
                gaps=candidate.improving_gap_count,
                sources=candidate.source_count,
                valuation="yes" if candidate.valuation_data_available else "no",
                note=candidate.review_note,
            )
        )
    lines.extend(
        [
            "",
            "## Status Explanations",
            "",
            "| Company | Status | Why | Upgrade Condition | Downgrade Trigger |",
            "|---|---|---|---|---|",
        ]
    )
    for candidate in result.candidates:
        lines.append(
            "| {company} | {status} | {why} | {upgrade} | {downgrade} |".format(
                company=candidate.company,
                status=candidate.status,
                why=candidate.why_this_status,
                upgrade=candidate.what_would_upgrade,
                downgrade=candidate.what_would_downgrade,
            )
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "- Scores use existing local evidence and thesis-gap artifacts only.",
            "- Strong evidence with missing valuation data is classified as thesis-improving or valuation-blocked.",
            "- Weak, stale, or undated source coverage blocks review-candidate status.",
            "- Risk warnings block or penalize the queue status.",
            "",
        ]
    )
    return "\n".join(lines)


def _transition_markdown(result: DiscoveryResult) -> str:
    lines = [
        "# AI Infrastructure Opportunity Transition Report",
        "",
        "This transition report compares the current deterministic review queue with the optional prior local run.",
        "",
        "| Company | Prior Status | Current Status | Status Change | Score Delta |",
        "|---|---|---|---|---:|",
    ]
    for candidate in result.candidates:
        lines.append(
            "| {company} | {prior} | {current} | {change} | {delta} |".format(
                company=candidate.company,
                prior=candidate.prior_status or "NO_PRIOR",
                current=candidate.current_status or candidate.status,
                change=candidate.status_change,
                delta=candidate.score_delta,
            )
        )
    lines.extend(
        [
            "",
            "Boundary: this is not investment advice and does not create action instructions.",
            "",
        ]
    )
    return "\n".join(lines)


def _warnings_markdown(result: DiscoveryResult) -> str:
    lines = [
        "# AI Infrastructure Opportunity Discovery Warnings",
        "",
        "This discovery run used existing local artifacts only.",
        "",
    ]
    if not result.warning_codes:
        lines.append("- No discovery warnings.")
    else:
        for code in result.warning_codes:
            lines.append(f"- `{code}`")
    lines.extend(
        [
            "",
            "Safety:",
            "",
            "- Not investment advice.",
            "- No PM prompt wiring.",
            "- No portfolio, broker, or client data.",
            "- No network, web, LLM, or market-data calls.",
            "",
        ]
    )
    return "\n".join(lines)


def _delta_row(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in DELTA_FIELDS}

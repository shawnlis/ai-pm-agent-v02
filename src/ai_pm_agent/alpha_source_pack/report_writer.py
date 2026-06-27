"""Markdown review report writer for Alpha Source Pack imports."""

from __future__ import annotations

from pathlib import Path

from .models import AlphaSourcePackImportResult, ImportedAlphaItem


REPORT_FILENAME = "alpha_source_pack_review.md"
REPLACEMENTS = {
    "sell-the-news": "event-fade",
    "sell the news": "event-fade",
}


def write_review_report(result: AlphaSourcePackImportResult, out_dir: Path | str) -> Path:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / REPORT_FILENAME
    path.write_text(render_review_report(result), encoding="utf-8")
    return path


def render_review_report(result: AlphaSourcePackImportResult) -> str:
    lines = [
        "# Alpha Source Pack Review Queue",
        "",
        "Review-first output only. This file organizes imported Alpha source-pack records for human review. It is not a PM decision memo and includes no execution instruction or allocation field.",
        "",
        "## Boundary",
        "",
        f"- Mode: {result.boundary['mode']}",
        f"- Autopm enabled: {str(result.boundary['autopm_enabled']).lower()}",
        f"- Portfolio context used: {str(result.boundary['portfolio_context_used']).lower()}",
        f"- Broker connection: {str(result.boundary['broker_connection']).lower()}",
        "",
        "## State Counts",
        "",
    ]
    for state, count in result.state_counts.items():
        lines.append(f"- {state}: {count}")
    if not result.state_counts:
        lines.append("- none")

    lines.extend(["", "## Imported Signals", ""])
    lines.extend(_item_lines(result.imported_signals))
    lines.extend(["", "## Imported Candidates", ""])
    lines.extend(_item_lines(result.imported_candidates))
    lines.extend(["", "## Evidence Quality", ""])
    lines.extend(_evidence_quality_lines(result))
    lines.extend(["", "## Missing Evidence", ""])
    lines.extend(_missing_evidence_lines(result))
    lines.extend(["", "## Red-team Objections", ""])
    lines.extend(_red_team_lines(result))
    lines.extend(["", "## What Would Upgrade / Downgrade", ""])
    lines.extend(_upgrade_downgrade_lines(result))
    return _sanitize("\n".join(lines) + "\n")


def _item_lines(items: tuple[ImportedAlphaItem, ...]) -> list[str]:
    if not items:
        return ["- none"]
    lines: list[str] = []
    for item in items:
        lines.extend(
            [
                f"- `{item.source_id}` {item.title}",
                f"  - State: {item.opportunity_state}",
                f"  - Source status: {item.source_status}; review status: {item.review_status}",
                f"  - Mapping reason: {item.mapping_reason}",
                f"  - Provenance refs: {', '.join(item.source_refs) or 'none'}",
            ]
        )
    return lines


def _evidence_quality_lines(result: AlphaSourcePackImportResult) -> list[str]:
    items = result.imported_signals + result.imported_candidates
    if not items:
        return ["- none"]
    return [
        f"- `{item.source_id}`: {item.evidence_quality}; quality audit: {item.quality_classification or 'not applicable'}"
        for item in items
    ]


def _missing_evidence_lines(result: AlphaSourcePackImportResult) -> list[str]:
    lines: list[str] = []
    for item in result.imported_signals + result.imported_candidates:
        if item.missing_evidence:
            lines.append(f"- `{item.source_id}`: {', '.join(item.missing_evidence)}")
    return lines or ["- none"]


def _red_team_lines(result: AlphaSourcePackImportResult) -> list[str]:
    lines = [
        f"- `{item.source_id}`: {item.red_team_objection or 'Not specified.'}"
        for item in result.imported_signals + result.imported_candidates
    ]
    return lines or ["- none"]


def _upgrade_downgrade_lines(result: AlphaSourcePackImportResult) -> list[str]:
    lines: list[str] = []
    for item in result.imported_signals + result.imported_candidates:
        lines.extend(
            [
                f"- `{item.source_id}`",
                f"  - Would upgrade: {item.what_would_upgrade or 'Additional reviewed evidence.'}",
                f"  - Would downgrade: {item.what_would_downgrade or 'Contradictory reviewed evidence.'}",
            ]
        )
    return lines or ["- none"]


def _sanitize(text: str) -> str:
    sanitized = text
    for raw, replacement in REPLACEMENTS.items():
        sanitized = sanitized.replace(raw, replacement).replace(raw.title(), replacement)
    return sanitized

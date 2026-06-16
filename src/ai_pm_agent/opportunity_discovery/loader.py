"""Load existing local evidence and thesis-gap artifacts for discovery."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import DiscoveryInputBundle, DiscoveryInputPaths


LEDGER_FILENAME = "company_evidence_ledger.csv"
METRIC_HISTORY_FILENAME = "metric_history.csv"
SOURCE_MANIFEST_FILENAME = "source_manifest.json"
THESIS_GAP_TABLE_FILENAME = "thesis_gap_table.csv"
THESIS_GAP_SUMMARY_FILENAME = "thesis_gap_summary.json"
SOURCE_COVERAGE_FILENAME = "source_coverage.csv"
MONITOR_WARNINGS_FILENAME = "monitor_warnings.md"


class MissingOpportunityInputError(RuntimeError):
    """Raised when opportunity discovery cannot safely load required inputs."""


def resolve_input_paths(
    *,
    evidence_dir: Path | str,
    monitor_dir: Path | str,
    prior_monitor_dir: Path | str | None = None,
) -> DiscoveryInputPaths:
    evidence_path = Path(evidence_dir)
    monitor_path = Path(monitor_dir)
    return DiscoveryInputPaths(
        evidence_dir=evidence_path,
        monitor_dir=monitor_path,
        ledger_csv=evidence_path / LEDGER_FILENAME,
        metric_history_csv=evidence_path / METRIC_HISTORY_FILENAME,
        source_manifest_json=evidence_path / SOURCE_MANIFEST_FILENAME,
        thesis_gap_table_csv=monitor_path / THESIS_GAP_TABLE_FILENAME,
        thesis_gap_summary_json=monitor_path / THESIS_GAP_SUMMARY_FILENAME,
        source_coverage_csv=monitor_path / SOURCE_COVERAGE_FILENAME,
        monitor_warnings_md=monitor_path / MONITOR_WARNINGS_FILENAME,
        prior_monitor_dir=Path(prior_monitor_dir) if prior_monitor_dir is not None else None,
    )


def load_from_paths(
    *,
    evidence_dir: Path | str,
    monitor_dir: Path | str,
    prior_monitor_dir: Path | str | None = None,
) -> DiscoveryInputBundle:
    paths = resolve_input_paths(
        evidence_dir=evidence_dir,
        monitor_dir=monitor_dir,
        prior_monitor_dir=prior_monitor_dir,
    )
    missing = [
        path
        for path in [
            paths.ledger_csv,
            paths.metric_history_csv,
            paths.source_manifest_json,
            paths.thesis_gap_table_csv,
            paths.thesis_gap_summary_json,
            paths.source_coverage_csv,
            paths.monitor_warnings_md,
        ]
        if not path.exists()
    ]
    if missing:
        raise MissingOpportunityInputError(
            "Missing required opportunity discovery inputs: " + ", ".join(str(path) for path in missing)
        )
    return DiscoveryInputBundle(
        paths=paths,
        ledger_rows=_read_csv(paths.ledger_csv),
        metric_rows=_read_csv(paths.metric_history_csv),
        source_manifest=_read_json_object(paths.source_manifest_json),
        thesis_gap_rows=_read_csv(paths.thesis_gap_table_csv),
        thesis_gap_summary=_read_json_object(paths.thesis_gap_summary_json),
        source_coverage_rows=_read_csv(paths.source_coverage_csv),
        monitor_warnings_text=paths.monitor_warnings_md.read_text(encoding="utf-8"),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: value or "" for key, value in row.items()} for row in reader]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MissingOpportunityInputError(f"Opportunity discovery JSON input is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise MissingOpportunityInputError(f"Opportunity discovery JSON input must be an object: {path}")
    return payload

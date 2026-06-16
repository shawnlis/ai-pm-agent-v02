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
PRIOR_SCORECARD_FILENAME = "opportunity_scorecard.json"
PRIOR_CANDIDATES_FILENAME = "opportunity_candidates.csv"


class MissingOpportunityInputError(RuntimeError):
    """Raised when opportunity discovery cannot safely load required inputs."""


def resolve_input_paths(
    *,
    evidence_dir: Path | str,
    monitor_dir: Path | str,
    prior_monitor_dir: Path | str | None = None,
    prior_scorecard_json: Path | str | None = None,
    prior_candidates_csv: Path | str | None = None,
    risk_summary_path: Path | str | None = None,
) -> DiscoveryInputPaths:
    evidence_path = Path(evidence_dir)
    monitor_path = Path(monitor_dir)
    prior_dir = _safe_optional_path(prior_monitor_dir)
    prior_scorecard = _safe_optional_path(prior_scorecard_json)
    prior_candidates = _safe_optional_path(prior_candidates_csv)
    if prior_dir is not None:
        prior_scorecard = prior_scorecard or _existing_optional(prior_dir / PRIOR_SCORECARD_FILENAME)
        prior_candidates = prior_candidates or _existing_optional(prior_dir / PRIOR_CANDIDATES_FILENAME)
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
        prior_monitor_dir=prior_dir,
        prior_scorecard_json=prior_scorecard,
        prior_candidates_csv=prior_candidates,
        risk_summary_path=_safe_optional_path(risk_summary_path),
    )


def load_from_paths(
    *,
    evidence_dir: Path | str,
    monitor_dir: Path | str,
    prior_monitor_dir: Path | str | None = None,
    prior_scorecard_json: Path | str | None = None,
    prior_candidates_csv: Path | str | None = None,
    risk_summary_path: Path | str | None = None,
) -> DiscoveryInputBundle:
    paths = resolve_input_paths(
        evidence_dir=evidence_dir,
        monitor_dir=monitor_dir,
        prior_monitor_dir=prior_monitor_dir,
        prior_scorecard_json=prior_scorecard_json,
        prior_candidates_csv=prior_candidates_csv,
        risk_summary_path=risk_summary_path,
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
        prior_candidate_rows=_read_prior_candidates(paths),
        risk_summary_rows=_read_risk_rows(paths.risk_summary_path),
        risk_summary_text=_read_optional_text(paths.risk_summary_path),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            {str(key).lstrip("\ufeff"): value or "" for key, value in row.items()}
            for row in reader
        ]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MissingOpportunityInputError(f"Opportunity discovery JSON input is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise MissingOpportunityInputError(f"Opportunity discovery JSON input must be an object: {path}")
    return payload


def _read_prior_candidates(paths: DiscoveryInputPaths) -> list[dict[str, str]]:
    if paths.prior_scorecard_json is not None and paths.prior_scorecard_json.exists():
        payload = _read_json_object(paths.prior_scorecard_json)
        candidates = payload.get("candidates", [])
        if isinstance(candidates, list):
            return [{str(key): str(value) for key, value in row.items()} for row in candidates if isinstance(row, dict)]
    if paths.prior_candidates_csv is not None and paths.prior_candidates_csv.exists():
        return _read_csv(paths.prior_candidates_csv)
    return []


def _read_risk_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    if path.suffix.lower() == ".json":
        payload = _read_json_object(path)
        rows = payload.get("warning_summary") or payload.get("warnings") or payload.get("risk_summary") or []
        if isinstance(rows, list):
            return [{str(key): str(value) for key, value in row.items()} for row in rows if isinstance(row, dict)]
        return []
    return []


def _read_optional_text(path: Path | None) -> str:
    if path is None or not path.exists() or path.suffix.lower() in {".csv", ".json"}:
        return ""
    return path.read_text(encoding="utf-8")


def _existing_optional(path: Path) -> Path | None:
    return path if path.exists() else None


def _safe_optional_path(path: Path | str | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    lowered = str(candidate).lower()
    basename = candidate.name.lower()
    parts = [part.lower() for part in candidate.parts]
    disallowed = (
        basename == "portfolio.csv"
        or any("ibkr positions" in part for part in parts)
        or any(marker in lowered for marker in ("broker", "client"))
    )
    if disallowed:
        raise MissingOpportunityInputError(
            "Unsafe optional opportunity discovery path rejected before reading contents: "
            f"{candidate}"
        )
    return candidate

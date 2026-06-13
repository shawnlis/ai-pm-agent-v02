"""Read existing SEC / IR Evidence Database export contracts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import EvidenceBundle, EvidenceInputPaths


LEDGER_FILENAME = "company_evidence_ledger.csv"
METRIC_HISTORY_FILENAME = "metric_history.csv"
SOURCE_MANIFEST_FILENAME = "source_manifest.json"
WARNINGS_FILENAME = "ingestion_warnings.md"
SQLITE_FILENAME = "evidence_db.sqlite"


class MissingEvidenceInputError(RuntimeError):
    """Raised when the monitor cannot safely read required evidence inputs."""


def resolve_input_paths(
    *,
    evidence_dir: Path | str | None = None,
    ledger_csv: Path | str | None = None,
    metric_history_csv: Path | str | None = None,
    source_manifest_json: Path | str | None = None,
    warnings_md: Path | str | None = None,
    evidence_db_sqlite: Path | str | None = None,
) -> EvidenceInputPaths:
    base_dir = Path(evidence_dir) if evidence_dir is not None else None
    if base_dir is not None:
        ledger = Path(ledger_csv) if ledger_csv is not None else base_dir / LEDGER_FILENAME
        metrics = Path(metric_history_csv) if metric_history_csv is not None else base_dir / METRIC_HISTORY_FILENAME
        manifest = Path(source_manifest_json) if source_manifest_json is not None else base_dir / SOURCE_MANIFEST_FILENAME
        warnings = Path(warnings_md) if warnings_md is not None else base_dir / WARNINGS_FILENAME
        sqlite_path = Path(evidence_db_sqlite) if evidence_db_sqlite is not None else base_dir / SQLITE_FILENAME
    else:
        ledger = Path(ledger_csv) if ledger_csv is not None else None
        metrics = Path(metric_history_csv) if metric_history_csv is not None else None
        manifest = Path(source_manifest_json) if source_manifest_json is not None else None
        warnings = Path(warnings_md) if warnings_md is not None else None
        sqlite_path = Path(evidence_db_sqlite) if evidence_db_sqlite is not None else None

    missing_names = []
    if ledger is None:
        missing_names.append("--ledger-csv or --evidence-dir")
    if metrics is None:
        missing_names.append("--metric-history-csv or --evidence-dir")
    if manifest is None:
        missing_names.append("--source-manifest-json or --evidence-dir")
    if missing_names:
        raise MissingEvidenceInputError("Missing required evidence input arguments: " + ", ".join(missing_names))

    return EvidenceInputPaths(
        ledger_csv=ledger,
        metric_history_csv=metrics,
        source_manifest_json=manifest,
        warnings_md=warnings if warnings and warnings.exists() else None,
        evidence_db_sqlite=sqlite_path if sqlite_path and sqlite_path.exists() else None,
    )


def load_evidence_bundle(input_paths: EvidenceInputPaths) -> EvidenceBundle:
    missing_paths = [
        path
        for path in [
            input_paths.ledger_csv,
            input_paths.metric_history_csv,
            input_paths.source_manifest_json,
        ]
        if not path.exists()
    ]
    if missing_paths:
        raise MissingEvidenceInputError(
            "Missing required evidence files: " + ", ".join(str(path) for path in missing_paths)
        )

    ledger_rows = _read_csv(input_paths.ledger_csv)
    metric_rows = _read_csv(input_paths.metric_history_csv)
    manifest = _read_json_object(input_paths.source_manifest_json)
    warnings_text = input_paths.warnings_md.read_text(encoding="utf-8") if input_paths.warnings_md else ""
    return EvidenceBundle(
        input_paths=input_paths,
        ledger_rows=ledger_rows,
        metric_rows=metric_rows,
        manifest=manifest,
        warnings_text=warnings_text,
    )


def load_from_paths(
    *,
    evidence_dir: Path | str | None = None,
    ledger_csv: Path | str | None = None,
    metric_history_csv: Path | str | None = None,
    source_manifest_json: Path | str | None = None,
    warnings_md: Path | str | None = None,
    evidence_db_sqlite: Path | str | None = None,
) -> EvidenceBundle:
    paths = resolve_input_paths(
        evidence_dir=evidence_dir,
        ledger_csv=ledger_csv,
        metric_history_csv=metric_history_csv,
        source_manifest_json=source_manifest_json,
        warnings_md=warnings_md,
        evidence_db_sqlite=evidence_db_sqlite,
    )
    return load_evidence_bundle(paths)


def manifest_warning_codes(manifest: dict[str, Any]) -> tuple[str, ...]:
    raw_codes = manifest.get("warning_codes", [])
    if not isinstance(raw_codes, list):
        return ()
    return tuple(sorted({str(code) for code in raw_codes if str(code)}))


def manifest_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sources = manifest.get("sources", [])
    return [source for source in sources if isinstance(source, dict)] if isinstance(sources, list) else []


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: value or "" for key, value in row.items()} for row in reader]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MissingEvidenceInputError(f"Evidence manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MissingEvidenceInputError(f"Evidence manifest must be a JSON object: {path}")
    return payload

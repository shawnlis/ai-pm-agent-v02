"""Fail-closed validation for Alpha Source Pack imports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import PACK_FILES


class AlphaSourcePackValidationError(RuntimeError):
    """Raised when an Alpha Source Pack cannot be safely imported."""


MANIFEST_REQUIRED = {"pack_version", "project_name", "export_date", "files", "counts", "excluded_counts"}
SIGNAL_REQUIRED = {
    "id",
    "title",
    "summary",
    "status",
    "review_status",
    "source_refs",
    "is_mock",
}
CANDIDATE_REQUIRED = {
    "candidate_id",
    "theme_name",
    "status",
    "review_status",
    "evidence_refs",
    "is_mock",
    "missing_evidence",
    "red_team_objection",
    "what_would_confirm",
    "what_would_falsify",
}
EVIDENCE_REQUIRED = {
    "id",
    "source_type",
    "source_name",
    "reliability",
    "review_status",
    "source_reference",
    "is_mock",
}
QUALITY_FIELDS = [
    "signal_id",
    "title",
    "claim_type",
    "status",
    "confidence_score",
    "allowed_max_status",
    "allowed_max_confidence",
    "classification",
    "issues",
    "missing_evidence",
    "confidence_cap_reason",
    "suggested_wording",
]
RAW_EVIDENCE_FIELDS = {"claim", "summary", "direct_quote", "notes", "raw_fetch_path"}
FORBIDDEN_FILE_NAMES = {".env", "Openrouter.txt"}
FORBIDDEN_MARKERS = ("SEC_USER_AGENT", "ALPHA_VANTAGE_API_KEY", "raw_fetch_path", "fetched_raw", "<html")
FORBIDDEN_PATH_PARTS = {
    ".env",
    "openrouter.txt",
    "ibkr positions",
    "credentials",
    "secrets",
    "portfolio.csv",
}


def resolve_source_pack_path(source_pack: Path) -> Path:
    raw_parts = [part.lower() for part in source_pack.parts]
    if ".." in source_pack.parts:
        raise AlphaSourcePackValidationError("source pack path must not contain parent traversal components")
    if any(part in FORBIDDEN_PATH_PARTS for part in raw_parts):
        raise AlphaSourcePackValidationError("source pack path contains a forbidden private-data path component")
    try:
        return source_pack.resolve(strict=True)
    except OSError as exc:
        raise AlphaSourcePackValidationError(f"source pack directory does not exist: {source_pack}") from exc


def require_pack_file_set(pack_path: Path) -> None:
    if not pack_path.exists() or not pack_path.is_dir():
        raise AlphaSourcePackValidationError(f"source pack directory does not exist: {pack_path}")
    actual = {path.name for path in pack_path.iterdir() if path.is_file()}
    missing = sorted(PACK_FILES - actual)
    unexpected = sorted(actual - PACK_FILES)
    if missing:
        raise AlphaSourcePackValidationError(f"source pack missing required files: {missing}")
    if unexpected:
        raise AlphaSourcePackValidationError(f"source pack contains unexpected files: {unexpected}")
    for name in actual:
        if name in FORBIDDEN_FILE_NAMES or name.endswith(".html") or name.endswith(".htm"):
            raise AlphaSourcePackValidationError(f"forbidden file in source pack: {name}")
    _validate_pack_files_stay_within_directory(pack_path)


def _validate_pack_files_stay_within_directory(pack_path: Path) -> None:
    pack_root = pack_path.resolve(strict=True)
    for file_name in PACK_FILES:
        file_path = pack_path / file_name
        try:
            resolved = file_path.resolve(strict=True)
        except OSError as exc:
            raise AlphaSourcePackValidationError(f"source pack file cannot be resolved: {file_name}") from exc
        if resolved.parent != pack_root:
            raise AlphaSourcePackValidationError(f"source pack file resolves outside source pack directory: {file_name}")


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlphaSourcePackValidationError(f"invalid JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise AlphaSourcePackValidationError(f"JSON file must contain an object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise AlphaSourcePackValidationError(f"{path}:{line_number}: invalid JSONL") from exc
            if not isinstance(payload, dict):
                raise AlphaSourcePackValidationError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(payload)
    return rows


def load_quality_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != QUALITY_FIELDS:
            raise AlphaSourcePackValidationError(f"quality_audit.csv fields are invalid: {reader.fieldnames}")
        return [{field: row.get(field, "") for field in QUALITY_FIELDS} for row in reader]


def validate_manifest(manifest: dict[str, Any]) -> None:
    _require_keys(manifest, MANIFEST_REQUIRED, "manifest.json")
    if manifest.get("pack_version") != "alpha-source-pack-v1":
        raise AlphaSourcePackValidationError("unsupported alpha source pack version")
    if manifest.get("project_name") != "alpha-research-team":
        raise AlphaSourcePackValidationError("source pack project_name must be alpha-research-team")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise AlphaSourcePackValidationError("manifest files must be an object")
    expected = PACK_FILES - {"manifest.json"}
    actual = set(files.values())
    if actual != expected:
        raise AlphaSourcePackValidationError(f"manifest file list does not match required pack files: {sorted(actual)}")


def validate_records(
    *,
    reviewed_signals: list[dict[str, Any]],
    theme_candidates: list[dict[str, Any]],
    evidence_manifest: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    quality_audit: list[dict[str, str]],
) -> None:
    evidence_ids = _validate_evidence_manifest(evidence_manifest)
    signal_ids = _validate_reviewed_signals(reviewed_signals, evidence_ids)
    _validate_theme_candidates(theme_candidates, evidence_ids)
    _validate_quality_audit(quality_audit, signal_ids)
    _validate_outcomes(outcomes, signal_ids)


def validate_no_forbidden_content(pack_path: Path) -> None:
    for path in pack_path.iterdir():
        if not path.is_file():
            raise AlphaSourcePackValidationError(f"source pack must not contain directories: {path.name}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in lowered:
                raise AlphaSourcePackValidationError(f"{path.name} contains forbidden marker: {marker}")


def _require_keys(record: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(record))
    if missing:
        raise AlphaSourcePackValidationError(f"{label} missing required keys: {missing}")


def _validate_reviewed_signals(signals: list[dict[str, Any]], evidence_ids: set[str]) -> set[str]:
    signal_ids: set[str] = set()
    for index, signal in enumerate(signals, start=1):
        label = f"reviewed_signals.jsonl:{index}"
        _require_keys(signal, SIGNAL_REQUIRED, label)
        if signal["id"] in signal_ids:
            raise AlphaSourcePackValidationError(f"duplicate exported signal id: {signal['id']}")
        signal_ids.add(signal["id"])
        if signal["review_status"] != "reviewed":
            raise AlphaSourcePackValidationError(f"{label} contains unreviewed signal: {signal['id']}")
        if signal["is_mock"] is not False:
            raise AlphaSourcePackValidationError(f"{label} contains mock signal: {signal['id']}")
        refs = signal["source_refs"]
        if not isinstance(refs, list) or not refs:
            raise AlphaSourcePackValidationError(f"{label} source_refs must be a non-empty list")
        missing = sorted(set(refs) - evidence_ids)
        if missing:
            raise AlphaSourcePackValidationError(f"{label} references missing evidence manifest rows: {missing}")
    return signal_ids


def _validate_theme_candidates(candidates: list[dict[str, Any]], evidence_ids: set[str]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        label = f"theme_candidates.jsonl:{index}"
        _require_keys(candidate, CANDIDATE_REQUIRED, label)
        if candidate["is_mock"] is not False:
            raise AlphaSourcePackValidationError(f"{label} contains mock candidate: {candidate['candidate_id']}")
        if candidate["status"] not in {"Watch", "Incubating"}:
            raise AlphaSourcePackValidationError(f"{label} has non-review-first candidate status: {candidate['status']}")
        if candidate["review_status"] not in {"draft", "reviewed"}:
            raise AlphaSourcePackValidationError(f"{label} has invalid candidate review_status: {candidate['review_status']}")
        refs = candidate["evidence_refs"]
        if not isinstance(refs, list):
            raise AlphaSourcePackValidationError(f"{label} evidence_refs must be a list")
        missing = sorted(set(refs) - evidence_ids)
        if missing:
            raise AlphaSourcePackValidationError(f"{label} references missing evidence manifest rows: {missing}")


def _validate_evidence_manifest(rows: list[dict[str, Any]]) -> set[str]:
    evidence_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        label = f"evidence_manifest.jsonl:{index}"
        _require_keys(row, EVIDENCE_REQUIRED, label)
        raw_fields = sorted(RAW_EVIDENCE_FIELDS & set(row))
        if raw_fields:
            raise AlphaSourcePackValidationError(f"{label} contains forbidden raw evidence fields: {raw_fields}")
        if row["is_mock"] is not False:
            raise AlphaSourcePackValidationError(f"{label} contains mock evidence: {row['id']}")
        if row["id"] in evidence_ids:
            raise AlphaSourcePackValidationError(f"duplicate evidence manifest id: {row['id']}")
        evidence_ids.add(row["id"])
    return evidence_ids


def _validate_quality_audit(rows: list[dict[str, str]], signal_ids: set[str]) -> None:
    for index, row in enumerate(rows, start=1):
        signal_id = row.get("signal_id", "")
        if signal_id and signal_id not in signal_ids:
            raise AlphaSourcePackValidationError(f"quality_audit.csv:{index} references non-exported signal: {signal_id}")


def _validate_outcomes(outcomes: list[dict[str, Any]], signal_ids: set[str]) -> None:
    for index, outcome in enumerate(outcomes, start=1):
        signal_id = outcome.get("signal_id")
        if signal_id not in signal_ids:
            raise AlphaSourcePackValidationError(f"outcomes.jsonl:{index} references non-exported signal: {signal_id}")

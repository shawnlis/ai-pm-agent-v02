"""Read Portfolio Risk Cockpit and Short Put Risk Monitor artifacts."""

from __future__ import annotations

import csv
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ai_pm_agent.portfolio_risk_cockpit import schema as portfolio_schema
from ai_pm_agent.risk_cockpit_pipeline.models import (
    ArtifactReadResult,
    ARTIFACT_READ_FAILED,
    MISSING_PORTFOLIO_ARTIFACT,
    MISSING_SHORT_PUT_ARTIFACT,
    RISK_ARTIFACT_NEEDS_REVIEW,
    RiskCockpitPipelineError,
    assert_safe_input_path,
    requires_review,
    unique_codes,
)
from ai_pm_agent.short_put_risk_monitor import schema as short_put_schema


PORTFOLIO_ARTIFACTS = [
    ("portfolio_summary", portfolio_schema.SUMMARY_FILENAME, "json"),
    ("portfolio_exposure_by_ticker", portfolio_schema.TICKER_EXPOSURE_FILENAME, "csv"),
    ("portfolio_exposure_by_theme", portfolio_schema.THEME_EXPOSURE_FILENAME, "csv"),
    ("portfolio_exposure_by_currency", portfolio_schema.CURRENCY_EXPOSURE_FILENAME, "csv"),
    ("portfolio_stress", portfolio_schema.STRESS_SCENARIOS_FILENAME, "csv"),
    ("portfolio_warnings", portfolio_schema.WARNINGS_FILENAME, "markdown"),
]

SHORT_PUT_ARTIFACTS = [
    ("short_put_summary", short_put_schema.SUMMARY_FILENAME, "json"),
    ("short_put_positions", short_put_schema.POSITIONS_FILENAME, "csv"),
    ("short_put_stress", short_put_schema.STRESS_FILENAME, "csv"),
    ("short_put_warnings", short_put_schema.WARNINGS_FILENAME, "markdown"),
]


def read_portfolio_artifacts(report_dir: str | Path) -> ArtifactReadResult:
    safe_dir = assert_safe_input_path(report_dir)
    rows, warnings, data = _read_artifacts(
        safe_dir,
        PORTFOLIO_ARTIFACTS,
        missing_code=MISSING_PORTFOLIO_ARTIFACT,
    )
    return ArtifactReadResult(
        artifact_rows=rows,
        warning_codes=warnings,
        portfolio_ticker_rows=data.get("portfolio_exposure_by_ticker", []),
    )


def read_short_put_artifacts(report_dir: str | Path) -> ArtifactReadResult:
    safe_dir = assert_safe_input_path(report_dir)
    rows, warnings, data = _read_artifacts(
        safe_dir,
        SHORT_PUT_ARTIFACTS,
        missing_code=MISSING_SHORT_PUT_ARTIFACT,
    )
    return ArtifactReadResult(
        artifact_rows=rows,
        warning_codes=warnings,
        short_put_position_rows=data.get("short_put_positions", []),
    )


def _read_artifacts(
    report_dir: Path,
    specs: list[tuple[str, str, str]],
    *,
    missing_code: str,
) -> tuple[list[dict[str, object]], list[str], dict[str, list[dict[str, str]]]]:
    artifact_rows: list[dict[str, object]] = []
    warning_codes: list[str] = []
    data: dict[str, list[dict[str, str]]] = {}

    for artifact_type, filename, kind in specs:
        path = report_dir / filename
        if not path.exists():
            warning_codes.append(missing_code)
            artifact_rows.append(
                _artifact_row(
                    artifact_type=artifact_type,
                    path=path,
                    exists=False,
                    status="missing",
                    row_count=0,
                    warning_count=1,
                    review_required=True,
                    notes=missing_code,
                )
            )
            continue

        if kind == "csv":
            csv_rows = _read_csv(path)
            data[artifact_type] = csv_rows
            codes = _warning_codes_from_rows(csv_rows)
            if codes:
                warning_codes.append(RISK_ARTIFACT_NEEDS_REVIEW)
            artifact_rows.append(
                _artifact_row(
                    artifact_type=artifact_type,
                    path=path,
                    exists=True,
                    status="review_required" if requires_review(codes) else "ok",
                    row_count=len(csv_rows),
                    warning_count=len(codes),
                    review_required=requires_review(codes),
                    notes=";".join(codes),
                )
            )
            continue

        if kind == "json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, JSONDecodeError) as exc:
                raise RiskCockpitPipelineError(f"{ARTIFACT_READ_FAILED}: failed to parse JSON artifact {path}") from exc
            if not isinstance(payload, dict):
                raise RiskCockpitPipelineError(f"{ARTIFACT_READ_FAILED}: JSON artifact {path} must contain an object")
            codes = [str(code) for code in payload.get("warning_codes", []) if code]
            if codes:
                warning_codes.append(RISK_ARTIFACT_NEEDS_REVIEW)
            artifact_rows.append(
                _artifact_row(
                    artifact_type=artifact_type,
                    path=path,
                    exists=True,
                    status="review_required" if requires_review(codes) else "ok",
                    row_count=1,
                    warning_count=len(codes),
                    review_required=requires_review(codes),
                    notes=";".join(codes),
                )
            )
            continue

        warning_count = _markdown_warning_count(path)
        artifact_rows.append(
            _artifact_row(
                artifact_type=artifact_type,
                path=path,
                exists=True,
                status="review_required" if warning_count else "ok",
                row_count=1,
                warning_count=warning_count,
                review_required=warning_count > 0,
                notes="markdown warning artifact",
            )
        )
        if warning_count:
            warning_codes.append(RISK_ARTIFACT_NEEDS_REVIEW)

    return artifact_rows, warning_codes, data


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise RiskCockpitPipelineError(f"{ARTIFACT_READ_FAILED}: CSV artifact {path} missing header row")
            rows: list[dict[str, str]] = []
            for row in reader:
                if None in row:
                    raise RiskCockpitPipelineError(
                        f"{ARTIFACT_READ_FAILED}: CSV artifact {path} contains unreadable columns"
                    )
                rows.append(dict(row))
            return rows
    except csv.Error as exc:
        raise RiskCockpitPipelineError(f"{ARTIFACT_READ_FAILED}: failed to parse CSV artifact {path}") from exc


def _warning_codes_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for row in rows:
        codes.extend(code for code in str(row.get("warning_codes", "")).split(";") if code)
        if str(row.get("review_status", "")).upper() == "NEEDS_REVIEW":
            codes.append(RISK_ARTIFACT_NEEDS_REVIEW)
    return unique_codes(codes)


def _markdown_warning_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    if "No warning codes" in text:
        return 0
    return sum(1 for line in text.splitlines() if line.strip().startswith("- `"))


def _artifact_row(
    *,
    artifact_type: str,
    path: Path,
    exists: bool,
    status: str,
    row_count: int,
    warning_count: int,
    review_required: bool,
    notes: str,
) -> dict[str, object]:
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "exists": exists,
        "status": status,
        "row_count": row_count,
        "warning_count": warning_count,
        "review_required": review_required,
        "notes": notes,
    }

"""Build pipeline index and warning summaries."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from ai_pm_agent.risk_cockpit_pipeline.models import (
    PIPELINE_REVIEW_REQUIRED,
    REVIEW_WARNING_CODES,
    SAFETY_BOUNDARY,
    SCHEMA_VERSION,
    requires_review,
    unique_codes,
)


def build_warning_summary(source_codes: dict[str, list[str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in [
        "portfolio_risk_cockpit",
        "short_put_risk_monitor",
        "market_data_fixture",
        "risk_cockpit_pipeline",
    ]:
        counts = Counter(code for code in source_codes.get(source, []) if code)
        for code in sorted(counts):
            rows.append(
                {
                    "source": source,
                    "warning_code": code,
                    "count": counts[code],
                    "review_required": code in REVIEW_WARNING_CODES,
                    "notes": _warning_note(code),
                }
            )
    return rows


def build_pipeline_index(
    *,
    run_id: str,
    generated_at: str,
    portfolio_report_dir: str,
    short_put_report_dir: str,
    portfolio_input_path: str,
    short_put_input_path: str,
    market_data_fixture_path: str,
    output_dir: str,
    portfolio_status: str,
    short_put_status: str,
    market_data_status: str,
    enrichment_status: str,
    files_created: list[str],
    warning_codes: list[str],
) -> dict[str, object]:
    review_required = requires_review(warning_codes)
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "schema_version": SCHEMA_VERSION,
        "portfolio_report_dir": portfolio_report_dir,
        "short_put_report_dir": short_put_report_dir,
        "portfolio_input_path": portfolio_input_path,
        "short_put_input_path": short_put_input_path,
        "market_data_fixture_path": market_data_fixture_path,
        "output_dir": output_dir,
        "portfolio_status": portfolio_status,
        "short_put_status": short_put_status,
        "market_data_status": market_data_status,
        "enrichment_status": enrichment_status,
        "files_created": files_created,
        "warning_codes": unique_codes(warning_codes),
        "review_required": review_required,
        "boundary": dict(SAFETY_BOUNDARY),
    }


def codes_from_rows(rows: Iterable[dict[str, object]]) -> list[str]:
    codes: list[str] = []
    for row in rows:
        codes.extend(code for code in str(row.get("warning_codes", "")).split(";") if code)
    return codes


def with_pipeline_review_code(codes: list[str]) -> list[str]:
    merged = list(codes)
    if requires_review(merged):
        merged.append(PIPELINE_REVIEW_REQUIRED)
    return unique_codes(merged)


def _warning_note(code: str) -> str:
    notes = {
        "MISSING_PORTFOLIO_ARTIFACT": "portfolio artifact is absent",
        "MISSING_SHORT_PUT_ARTIFACT": "short put artifact is absent",
        "MISSING_MARKET_DATA": "fixture market data is absent for a ticker",
        "STALE_MARKET_DATA": "fixture market data is older than the configured age",
        "PRICE_MISMATCH_NEEDS_REVIEW": "source price differs from fixture market data",
        "MARKET_DATA_FIXTURE_ONLY": "market data came from a local fixture",
        "RISK_ARTIFACT_NEEDS_REVIEW": "source risk artifact contains review warnings",
        "PIPELINE_REVIEW_REQUIRED": "pipeline output requires manual review",
        "DISALLOWED_REAL_DATA_PATH": "real-data-looking path was rejected",
        "NO_LIVE_MARKET_DATA": "no live market data provider was used",
    }
    return notes.get(code, "")

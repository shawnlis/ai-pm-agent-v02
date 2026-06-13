"""Structured warning codes for SEC / IR evidence ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import IngestionWarning, stable_id, utc_now


MISSING_CIK = "MISSING_CIK"
MISSING_FILING_DATE = "MISSING_FILING_DATE"
MISSING_FACT_VALUE = "MISSING_FACT_VALUE"
UNSUPPORTED_FACT_UNIT = "UNSUPPORTED_FACT_UNIT"
STALE_SOURCE = "STALE_SOURCE"
UNKNOWN_COMPANY = "UNKNOWN_COMPANY"
PARSE_ERROR = "PARSE_ERROR"
SOURCE_FIXTURE_ONLY = "SOURCE_FIXTURE_ONLY"
SEC_USER_AGENT_REQUIRED = "SEC_USER_AGENT_REQUIRED"
SEC_LIVE_FETCH_NOT_ENABLED = "SEC_LIVE_FETCH_NOT_ENABLED"
SEC_OFFLINE_MODE_NETWORK_BLOCKED = "SEC_OFFLINE_MODE_NETWORK_BLOCKED"
SEC_HTTP_ERROR = "SEC_HTTP_ERROR"
SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED = "SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED"
SEC_CACHE_HIT = "SEC_CACHE_HIT"
SEC_CACHE_MISS = "SEC_CACHE_MISS"
SEC_CACHE_STALE = "SEC_CACHE_STALE"
SEC_CIK_RESOLUTION_FAILED = "SEC_CIK_RESOLUTION_FAILED"
SEC_INVALID_RESPONSE = "SEC_INVALID_RESPONSE"
SEC_COMPANYFACTS_NOT_FOUND = "SEC_COMPANYFACTS_NOT_FOUND"
SEC_SUBMISSIONS_NOT_FOUND = "SEC_SUBMISSIONS_NOT_FOUND"
SEC_LIVE_FETCH_USED = "SEC_LIVE_FETCH_USED"
SEC_FETCH_FAIL_CLOSED = "SEC_FETCH_FAIL_CLOSED"

WARNING_CODES = {
    MISSING_CIK,
    MISSING_FILING_DATE,
    MISSING_FACT_VALUE,
    UNSUPPORTED_FACT_UNIT,
    STALE_SOURCE,
    UNKNOWN_COMPANY,
    PARSE_ERROR,
    SOURCE_FIXTURE_ONLY,
    SEC_USER_AGENT_REQUIRED,
    SEC_LIVE_FETCH_NOT_ENABLED,
    SEC_OFFLINE_MODE_NETWORK_BLOCKED,
    SEC_HTTP_ERROR,
    SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED,
    SEC_CACHE_HIT,
    SEC_CACHE_MISS,
    SEC_CACHE_STALE,
    SEC_CIK_RESOLUTION_FAILED,
    SEC_INVALID_RESPONSE,
    SEC_COMPANYFACTS_NOT_FOUND,
    SEC_SUBMISSIONS_NOT_FOUND,
    SEC_LIVE_FETCH_USED,
    SEC_FETCH_FAIL_CLOSED,
}


def make_warning(
    code: str,
    message: str,
    *,
    run_id: str = "",
    source_path: str | Path | None = None,
    context: dict[str, Any] | None = None,
) -> IngestionWarning:
    """Build a stable warning record without exposing local secret content."""

    if code not in WARNING_CODES:
        raise ValueError(f"Unsupported evidence DB warning code: {code}")
    source_text = str(source_path) if source_path is not None else ""
    context_json = json.dumps(context or {}, sort_keys=True)
    return IngestionWarning(
        warning_id=stable_id("warning", run_id, code, message, source_text, context_json),
        run_id=run_id,
        code=code,
        message=message,
        source_path=source_text,
        context_json=context_json,
        created_at=utc_now(),
    )


def with_run_id(warning: IngestionWarning, run_id: str) -> IngestionWarning:
    """Attach a run id and regenerate the warning id for repository insertion."""

    return IngestionWarning(
        warning_id=stable_id(
            "warning",
            run_id,
            warning.code,
            warning.message,
            warning.source_path,
            warning.context_json,
        ),
        run_id=run_id,
        code=warning.code,
        message=warning.message,
        source_path=warning.source_path,
        context_json=warning.context_json,
        created_at=warning.created_at,
    )

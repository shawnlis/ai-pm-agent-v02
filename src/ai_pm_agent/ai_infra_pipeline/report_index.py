"""Pipeline index writer for AI infrastructure evidence-to-monitor runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_pm_agent.evidence_db.models import utc_now


PIPELINE_INDEX_FILENAME = "AI_INFRA_PIPELINE_INDEX.json"

BOUNDARY_FIELDS = {
    "no_live_sec_fetch": True,
    "no_web_search": True,
    "no_llm": True,
    "no_yfinance": True,
    "no_portfolio_data": True,
    "no_broker_data": True,
    "no_client_data": True,
    "no_pm_recommendation_wiring": True,
}


def write_pipeline_index(
    *,
    output_dir: Path | str,
    run_id: str,
    companies: list[str],
    evidence_input_dir: Path | str | None,
    batch_output_dir: Path | str | None,
    monitor_output_dir: Path | str | None,
    batch_status: str,
    monitor_status: str,
    files_created: list[str],
    warning_codes: list[str],
    error_message: str = "",
) -> dict[str, Any]:
    """Write the stable pipeline index contract and return its payload."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    index_path = target / PIPELINE_INDEX_FILENAME
    payload: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "companies": companies,
        "evidence_input_dir": _path_text(evidence_input_dir),
        "batch_output_dir": _path_text(batch_output_dir),
        "monitor_output_dir": _path_text(monitor_output_dir),
        "batch_status": batch_status,
        "monitor_status": monitor_status,
        "files_created": sorted(set(files_created + [str(index_path)])),
        "warning_codes": sorted(set(warning_codes)),
        "error_message": error_message,
    }
    payload.update(BOUNDARY_FIELDS)
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _path_text(path: Path | str | None) -> str:
    return "" if path is None else str(path)

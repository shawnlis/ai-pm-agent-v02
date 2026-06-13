"""Offline orchestration from Evidence DB exports to Thesis-Gap Monitor v2."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

from ai_pm_agent.evidence_db.batch_runner import AI_INFRA_CORE_UNIVERSE, DEFAULT_BATCH_OUTPUT_DIR, run_batch
from ai_pm_agent.evidence_db.models import stable_id, utc_now
from ai_pm_agent.thesis_gap_monitor.evidence_reader import MissingEvidenceInputError
from ai_pm_agent.thesis_gap_monitor.models import DEFAULT_COMPANIES
from ai_pm_agent.thesis_gap_monitor.report_writer import default_output_dir
from ai_pm_agent.thesis_gap_monitor.runner import run_monitor

from .report_index import PIPELINE_INDEX_FILENAME, write_pipeline_index


DEFAULT_PIPELINE_BATCH_DIR = DEFAULT_BATCH_OUTPUT_DIR
WARNING_MONITOR_NOT_RUN = "MONITOR_NOT_RUN"
WARNING_BATCH_NOT_RUN = "BATCH_NOT_RUN"


class PipelineConfigError(ValueError):
    """Raised when a pipeline request would cross a safety boundary or lacks inputs."""


def run_pipeline(
    *,
    evidence_dir: Path | str | None = None,
    batch_out_dir: Path | str | None = None,
    monitor_out_dir: Path | str | None = None,
    run_batch_dry_run: bool = False,
    run_monitor_step: bool = False,
    offline: bool = False,
    as_of_date: date | None = None,
    companies: list[str] | None = None,
) -> dict[str, Any]:
    """Run the offline-first AI infrastructure evidence-to-monitor pipeline."""

    selected_companies = [company.strip().upper() for company in (companies or DEFAULT_COMPANIES) if company.strip()]
    if not selected_companies:
        raise PipelineConfigError("At least one company ticker is required.")

    evidence_path = Path(evidence_dir) if evidence_dir is not None else None
    batch_dir = Path(batch_out_dir) if batch_out_dir is not None else DEFAULT_PIPELINE_BATCH_DIR
    monitor_dir = Path(monitor_out_dir) if monitor_out_dir is not None else default_output_dir()
    should_run_monitor = run_monitor_step or (evidence_path is not None and not run_batch_dry_run)
    if not run_batch_dry_run and not should_run_monitor:
        raise PipelineConfigError("Provide --evidence-dir or --run-batch-dry-run.")
    if should_run_monitor and evidence_path is None:
        raise PipelineConfigError("--run-monitor requires --evidence-dir.")
    if should_run_monitor and evidence_path is not None and not evidence_path.exists():
        raise MissingEvidenceInputError(f"Evidence input directory does not exist: {evidence_path}")

    run_id = stable_id("ai_infra_pipeline", utc_now(), ",".join(selected_companies), str(evidence_path or ""))
    files_created: list[str] = []
    warning_codes: list[str] = []
    batch_status = "not_run"
    monitor_status = "not_run"
    batch_result: dict[str, Any] | None = None
    monitor_result: dict[str, Any] | None = None

    if run_batch_dry_run:
        batch_result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=selected_companies,
            out_dir=batch_dir,
            dry_run=True,
            offline=offline,
        )
        batch_status = str(batch_result.get("status") or "unknown")
        files_created.extend(_output_paths(batch_result.get("outputs")))
        warning_codes.extend(batch_result.get("manifest", {}).get("warning_codes", []))
    else:
        warning_codes.append(WARNING_BATCH_NOT_RUN)

    if should_run_monitor:
        monitor_result = run_monitor(
            evidence_dir=evidence_path,
            out_dir=monitor_dir,
            tickers=selected_companies,
            as_of_date=as_of_date,
        )
        monitor_status = "completed"
        files_created.extend(_output_paths(monitor_result.get("outputs")))
        warning_codes.extend(monitor_result.get("warning_codes", []))
    else:
        warning_codes.append(WARNING_MONITOR_NOT_RUN)

    index_dir = monitor_dir if should_run_monitor else batch_dir
    index = write_pipeline_index(
        output_dir=index_dir,
        run_id=run_id,
        companies=selected_companies,
        evidence_input_dir=evidence_path,
        batch_output_dir=batch_dir if run_batch_dry_run else None,
        monitor_output_dir=monitor_dir if should_run_monitor else None,
        batch_status=batch_status,
        monitor_status=monitor_status,
        files_created=files_created,
        warning_codes=warning_codes,
    )
    return {
        "status": _pipeline_status(batch_status=batch_status, monitor_status=monitor_status, run_monitor_step=should_run_monitor),
        "run_id": run_id,
        "index": index,
        "outputs": {"pipeline_index": str(index_dir / PIPELINE_INDEX_FILENAME)},
        "batch": batch_result,
        "monitor": monitor_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline AI infra Evidence DB to Thesis-Gap Monitor pipeline.")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--batch-out-dir", type=Path, default=DEFAULT_PIPELINE_BATCH_DIR)
    parser.add_argument("--monitor-out-dir", type=Path)
    parser.add_argument("--run-batch-dry-run", action="store_true")
    parser.add_argument("--run-monitor", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--as-of-date", help="YYYY-MM-DD date for monitor freshness checks.")
    parser.add_argument("--companies", nargs="+", default=DEFAULT_COMPANIES)
    args = parser.parse_args(argv)

    try:
        as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    except ValueError:
        print("--as-of-date must use YYYY-MM-DD format.", file=sys.stderr)
        return 2

    try:
        result = run_pipeline(
            evidence_dir=args.evidence_dir,
            batch_out_dir=args.batch_out_dir,
            monitor_out_dir=args.monitor_out_dir,
            run_batch_dry_run=args.run_batch_dry_run,
            run_monitor_step=args.run_monitor,
            offline=args.offline,
            as_of_date=as_of,
            companies=args.companies,
        )
    except (MissingEvidenceInputError, PipelineConfigError) as exc:
        print(f"AI infra pipeline failed closed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"status": result["status"], "run_id": result["run_id"], "outputs": result["outputs"]}, indent=2, sort_keys=True))
    return 0


def _output_paths(outputs: Any) -> list[str]:
    if not isinstance(outputs, dict):
        return []
    return [str(path) for path in outputs.values() if path]


def _pipeline_status(*, batch_status: str, monitor_status: str, run_monitor_step: bool) -> str:
    if run_monitor_step and monitor_status != "completed":
        return "failed"
    if batch_status in {"completed_with_failures", "failed"}:
        return "completed_with_warnings"
    if batch_status == "planned" and monitor_status == "not_run":
        return "planned"
    if monitor_status == "completed":
        return "completed"
    return "completed_with_warnings"

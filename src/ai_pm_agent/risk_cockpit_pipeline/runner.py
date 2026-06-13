"""Offline Risk Cockpit Pipeline runner."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
import sys
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from ai_pm_agent.portfolio_risk_cockpit.runner import run_cockpit
from ai_pm_agent.risk_cockpit_pipeline.artifact_reader import (
    read_portfolio_artifacts,
    read_short_put_artifacts,
)
from ai_pm_agent.risk_cockpit_pipeline.enrichment import build_enrichment_rows
from ai_pm_agent.risk_cockpit_pipeline.fixture_market_data import (
    load_fixture_market_data,
    market_data_snapshot_rows,
)
from ai_pm_agent.risk_cockpit_pipeline.handoff_index import (
    build_pipeline_index,
    build_warning_summary,
    codes_from_rows,
    with_pipeline_review_code,
)
from ai_pm_agent.risk_cockpit_pipeline.models import (
    ARTIFACT_READ_FAILED,
    FOUNDATION_REPORT_FAILED,
    MARKET_DATA_FIXTURE_ONLY,
    MARKET_DATA_LOAD_FAILED,
    NO_LIVE_MARKET_DATA,
    PIPELINE_FAILED_CLOSED,
    RiskCockpitPipelineError,
    RiskCockpitPipelineFailure,
    RiskCockpitPipelineResult,
    assert_safe_input_path,
    requires_review,
    unique_codes,
)
from ai_pm_agent.risk_cockpit_pipeline.report_writer import default_output_dir, write_outputs
from ai_pm_agent.risk_cockpit_pipeline.schema import INDEX_FILENAME
from ai_pm_agent.short_put_risk_monitor.runner import run_monitor


def run_pipeline(
    *,
    portfolio_report_dir: str | Path | None = None,
    short_put_report_dir: str | Path | None = None,
    portfolio_input: str | Path | None = None,
    short_put_input: str | Path | None = None,
    market_data_fixture: str | Path,
    out_dir: str | Path | None = None,
    run_foundation_reports: bool = False,
    as_of_date: str | None = None,
    max_market_data_age_days: int = 7,
    price_mismatch_threshold_pct: float = 0.05,
) -> RiskCockpitPipelineResult:
    report_date = as_of_date or date.today().isoformat()
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    run_id = f"risk-cockpit-v052-{uuid4().hex[:12]}"
    generated_at = datetime.now(UTC).isoformat()
    market_fixture_path = assert_safe_input_path(market_data_fixture)

    portfolio_input_text = ""
    short_put_input_text = ""
    files_created: list[str] = []
    portfolio_status = "not_started"
    short_put_status = "not_started"
    market_data_status = "not_started"
    enrichment_status = "not_started"
    if run_foundation_reports:
        if portfolio_input is None or short_put_input is None:
            raise RiskCockpitPipelineError("--run-foundation-reports requires --portfolio-input and --short-put-input")
        portfolio_input_path = assert_safe_input_path(portfolio_input)
        short_put_input_path = assert_safe_input_path(short_put_input)
        portfolio_input_text = str(portfolio_input_path)
        short_put_input_text = str(short_put_input_path)
        portfolio_dir = target / "portfolio_risk_cockpit"
        short_put_dir = target / "short_put_risk_monitor"
        try:
            portfolio_result = run_cockpit(input_path=portfolio_input_path, out_dir=portfolio_dir, as_of_date=report_date)
        except Exception as exc:
            _fail_closed(
                target=target,
                run_id=run_id,
                generated_at=generated_at,
                portfolio_report_dir=str(portfolio_dir),
                short_put_report_dir=str(short_put_dir),
                portfolio_input_path=portfolio_input_text,
                short_put_input_path=short_put_input_text,
                market_data_fixture_path=str(market_fixture_path),
                portfolio_status="failed",
                short_put_status=short_put_status,
                market_data_status=market_data_status,
                enrichment_status=enrichment_status,
                files_created=files_created,
                warning_codes=[FOUNDATION_REPORT_FAILED],
                error_message=str(exc),
            )
        files_created.extend(portfolio_result.files.values())
        portfolio_status = "generated"
        try:
            short_put_result = run_monitor(input_path=short_put_input_path, out_dir=short_put_dir, as_of_date=report_date)
        except Exception as exc:
            _fail_closed(
                target=target,
                run_id=run_id,
                generated_at=generated_at,
                portfolio_report_dir=str(portfolio_dir),
                short_put_report_dir=str(short_put_dir),
                portfolio_input_path=portfolio_input_text,
                short_put_input_path=short_put_input_text,
                market_data_fixture_path=str(market_fixture_path),
                portfolio_status=portfolio_status,
                short_put_status="failed",
                market_data_status=market_data_status,
                enrichment_status=enrichment_status,
                files_created=files_created,
                warning_codes=[FOUNDATION_REPORT_FAILED],
                error_message=str(exc),
            )
        files_created.extend(short_put_result.files.values())
        short_put_status = "generated"
    else:
        if portfolio_report_dir is None or short_put_report_dir is None:
            raise RiskCockpitPipelineError(
                "existing-artifact mode requires --portfolio-report-dir and --short-put-report-dir"
            )
        portfolio_dir = assert_safe_input_path(portfolio_report_dir)
        short_put_dir = assert_safe_input_path(short_put_report_dir)
        portfolio_status = "pending"
        short_put_status = "pending"

    try:
        portfolio_artifacts = read_portfolio_artifacts(portfolio_dir)
    except Exception as exc:
        _fail_closed(
            target=target,
            run_id=run_id,
            generated_at=generated_at,
            portfolio_report_dir=str(portfolio_dir),
            short_put_report_dir=str(short_put_dir),
            portfolio_input_path=portfolio_input_text,
            short_put_input_path=short_put_input_text,
            market_data_fixture_path=str(market_fixture_path),
            portfolio_status="failed",
            short_put_status=short_put_status,
            market_data_status=market_data_status,
            enrichment_status=enrichment_status,
            files_created=files_created,
            warning_codes=[ARTIFACT_READ_FAILED],
            error_message=str(exc),
        )
    portfolio_status = _status_from_codes(portfolio_artifacts.warning_codes)
    try:
        short_put_artifacts = read_short_put_artifacts(short_put_dir)
    except Exception as exc:
        _fail_closed(
            target=target,
            run_id=run_id,
            generated_at=generated_at,
            portfolio_report_dir=str(portfolio_dir),
            short_put_report_dir=str(short_put_dir),
            portfolio_input_path=portfolio_input_text,
            short_put_input_path=short_put_input_text,
            market_data_fixture_path=str(market_fixture_path),
            portfolio_status=portfolio_status,
            short_put_status="failed",
            market_data_status=market_data_status,
            enrichment_status=enrichment_status,
            files_created=files_created,
            warning_codes=[ARTIFACT_READ_FAILED],
            error_message=str(exc),
        )
    short_put_status = _status_from_codes(short_put_artifacts.warning_codes)
    try:
        market_snapshot = load_fixture_market_data(market_fixture_path)
    except Exception as exc:
        _fail_closed(
            target=target,
            run_id=run_id,
            generated_at=generated_at,
            portfolio_report_dir=str(portfolio_dir),
            short_put_report_dir=str(short_put_dir),
            portfolio_input_path=portfolio_input_text,
            short_put_input_path=short_put_input_text,
            market_data_fixture_path=str(market_fixture_path),
            portfolio_status=portfolio_status,
            short_put_status=short_put_status,
            market_data_status="failed",
            enrichment_status=enrichment_status,
            files_created=files_created,
            warning_codes=[MARKET_DATA_LOAD_FAILED],
            error_message=str(exc),
        )
    market_rows = market_data_snapshot_rows(market_snapshot)
    market_data_status = "loaded"
    try:
        enrichment_rows = build_enrichment_rows(
            portfolio_ticker_rows=portfolio_artifacts.portfolio_ticker_rows,
            short_put_position_rows=short_put_artifacts.short_put_position_rows,
            market_points=market_snapshot.points,
            as_of_date=report_date,
            max_market_data_age_days=max_market_data_age_days,
            price_mismatch_threshold_pct=price_mismatch_threshold_pct,
        )
    except Exception as exc:
        _fail_closed(
            target=target,
            run_id=run_id,
            generated_at=generated_at,
            portfolio_report_dir=str(portfolio_dir),
            short_put_report_dir=str(short_put_dir),
            portfolio_input_path=portfolio_input_text,
            short_put_input_path=short_put_input_text,
            market_data_fixture_path=str(market_fixture_path),
            portfolio_status=portfolio_status,
            short_put_status=short_put_status,
            market_data_status=market_data_status,
            enrichment_status="failed",
            files_created=files_created,
            warning_codes=[],
            error_message=str(exc),
        )

    source_codes = {
        "portfolio_risk_cockpit": portfolio_artifacts.warning_codes,
        "short_put_risk_monitor": short_put_artifacts.warning_codes,
        "market_data_fixture": list(market_snapshot.warning_codes),
        "risk_cockpit_pipeline": codes_from_rows(enrichment_rows),
    }
    all_codes = with_pipeline_review_code(
        source_codes["portfolio_risk_cockpit"]
        + source_codes["short_put_risk_monitor"]
        + source_codes["market_data_fixture"]
        + source_codes["risk_cockpit_pipeline"]
    )
    source_codes["risk_cockpit_pipeline"].extend(code for code in all_codes if code == "PIPELINE_REVIEW_REQUIRED")
    warning_rows = build_warning_summary(source_codes)
    artifact_rows = portfolio_artifacts.artifact_rows + short_put_artifacts.artifact_rows
    artifact_rows.append(_market_data_artifact_row(target, market_rows))

    portfolio_status = _status_from_codes(portfolio_artifacts.warning_codes)
    short_put_status = _status_from_codes(short_put_artifacts.warning_codes)
    market_data_status = _status_from_codes(codes_from_rows(market_rows) + [MARKET_DATA_FIXTURE_ONLY, NO_LIVE_MARKET_DATA])
    enrichment_status = _status_from_codes(codes_from_rows(enrichment_rows))

    index = build_pipeline_index(
        run_id=run_id,
        generated_at=generated_at,
        portfolio_report_dir=str(portfolio_dir),
        short_put_report_dir=str(short_put_dir),
        portfolio_input_path=portfolio_input_text,
        short_put_input_path=short_put_input_text,
        market_data_fixture_path=str(market_fixture_path),
        output_dir=str(target),
        portfolio_status=portfolio_status,
        short_put_status=short_put_status,
        market_data_status=market_data_status,
        enrichment_status=enrichment_status,
        files_created=[],
        warning_codes=all_codes,
    )
    result = RiskCockpitPipelineResult(
        run_id=run_id,
        generated_at=generated_at,
        as_of_date=report_date,
        output_dir=str(target),
        portfolio_report_dir=str(portfolio_dir),
        short_put_report_dir=str(short_put_dir),
        portfolio_input_path=portfolio_input_text,
        short_put_input_path=short_put_input_text,
        market_data_fixture_path=str(market_fixture_path),
        index=index,
        artifact_rows=artifact_rows,
        warning_rows=warning_rows,
        market_data_rows=market_rows,
        enrichment_rows=enrichment_rows,
        warning_codes=unique_codes(all_codes),
        review_required=requires_review(all_codes),
    )
    files = write_outputs(result, out_dir=target)
    return RiskCockpitPipelineResult(**{**result.__dict__, "files": files})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an offline Risk Cockpit Pipeline handoff.")
    parser.add_argument("--portfolio-report-dir", help="Existing Portfolio Risk Cockpit report directory.")
    parser.add_argument("--short-put-report-dir", help="Existing Short Put Risk Monitor report directory.")
    parser.add_argument("--portfolio-input", help="Portfolio Risk Cockpit fixture input for foundation report mode.")
    parser.add_argument("--short-put-input", help="Short Put Risk Monitor fixture input for foundation report mode.")
    parser.add_argument("--market-data-fixture", required=True, help="Local fixture market data CSV.")
    parser.add_argument("--out-dir", help="Output directory. Defaults under ignored reports/ path.")
    parser.add_argument("--run-foundation-reports", action="store_true", help="Run local fixture reports first.")
    parser.add_argument("--as-of-date", help="As-of date to stamp in outputs, YYYY-MM-DD.")
    parser.add_argument("--max-market-data-age-days", type=int, default=7)
    parser.add_argument("--price-mismatch-threshold-pct", type=float, default=0.05)
    parser.add_argument("--offline", action="store_true", help="Accepted for explicit safety; this runner is offline-only.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = run_pipeline(
            portfolio_report_dir=args.portfolio_report_dir,
            short_put_report_dir=args.short_put_report_dir,
            portfolio_input=args.portfolio_input,
            short_put_input=args.short_put_input,
            market_data_fixture=args.market_data_fixture,
            out_dir=args.out_dir,
            run_foundation_reports=args.run_foundation_reports,
            as_of_date=args.as_of_date,
            max_market_data_age_days=args.max_market_data_age_days,
            price_mismatch_threshold_pct=args.price_mismatch_threshold_pct,
        )
    except RiskCockpitPipelineFailure as exc:
        suffix = f" index: {exc.index_path}" if exc.index_path else ""
        print(f"Risk Cockpit Pipeline failed closed: {exc}{suffix}", file=sys.stderr)
        return 2
    except (RiskCockpitPipelineError, ValueError) as exc:
        print(f"Risk Cockpit Pipeline failed closed: {exc}", file=sys.stderr)
        return 2

    print(f"Risk Cockpit Pipeline wrote {len(result.files)} files")
    for label, path in sorted(result.files.items()):
        print(f"{label}: {path}")
    return 0


def _market_data_artifact_row(target: Path, market_rows: list[dict[str, object]]) -> dict[str, object]:
    warning_count = len(codes_from_rows(market_rows))
    return {
        "artifact_type": "market_data_snapshot",
        "path": str(target / "market_data_snapshot.csv"),
        "exists": True,
        "status": "ok",
        "row_count": len(market_rows),
        "warning_count": warning_count,
        "review_required": False,
        "notes": "fixture market data snapshot",
    }


def _status_from_codes(codes: list[str]) -> str:
    return "review_required" if requires_review(codes) else "ok"


def _fail_closed(
    *,
    target: Path,
    run_id: str,
    generated_at: str,
    portfolio_report_dir: str,
    short_put_report_dir: str,
    portfolio_input_path: str,
    short_put_input_path: str,
    market_data_fixture_path: str,
    portfolio_status: str,
    short_put_status: str,
    market_data_status: str,
    enrichment_status: str,
    files_created: list[str],
    warning_codes: list[str],
    error_message: str,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    index_path = target / INDEX_FILENAME
    merged_codes = unique_codes([PIPELINE_FAILED_CLOSED, *warning_codes])
    index = build_pipeline_index(
        run_id=run_id,
        generated_at=generated_at,
        portfolio_report_dir=portfolio_report_dir,
        short_put_report_dir=short_put_report_dir,
        portfolio_input_path=portfolio_input_path,
        short_put_input_path=short_put_input_path,
        market_data_fixture_path=market_data_fixture_path,
        output_dir=str(target),
        portfolio_status=portfolio_status,
        short_put_status=short_put_status,
        market_data_status=market_data_status,
        enrichment_status=enrichment_status,
        files_created=unique_codes([*files_created, str(index_path)]),
        warning_codes=merged_codes,
        error_message=error_message,
    )
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raise RiskCockpitPipelineFailure(
        f"{PIPELINE_FAILED_CLOSED}: {error_message}",
        index_path=str(index_path),
    )

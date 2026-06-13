"""Batch orchestration for SEC / IR evidence imports."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from .cache import DEFAULT_SEC_CACHE_DIR
from .exports import export_all
from .models import utc_now
from .repository import DEFAULT_DB_PATH, EvidenceRepository
from .sec_edgar import import_fixtures, import_live_sec


DEFAULT_BATCH_OUTPUT_DIR = Path("reports") / "sec_ir_evidence_db" / "ai_infra_coverage_batch"
AI_INFRA_CORE_UNIVERSE = "ai_infra_core"
AI_INFRA_CORE_COMPANIES: tuple[tuple[str, str], ...] = (
    ("MU", "Micron Technology"),
    ("NVDA", "NVIDIA"),
    ("AMD", "Advanced Micro Devices"),
    ("AVGO", "Broadcom"),
    ("MSFT", "Microsoft"),
    ("GOOGL", "Alphabet"),
)

BATCH_MANIFEST_FILENAME = "batch_manifest.json"
BATCH_WARNINGS_FILENAME = "batch_warnings.md"
COMPANY_RUN_SUMMARY_FILENAME = "company_run_summary.csv"

COMPANY_SUMMARY_FIELDS = [
    "ticker",
    "company_name",
    "status",
    "filings_count",
    "facts_count",
    "warnings_count",
    "newest_source_date",
    "output_dir",
    "warning_codes",
]

WARNING_BATCH_DRY_RUN = "BATCH_DRY_RUN"
WARNING_BATCH_EXPORT_ONLY = "BATCH_EXPORT_ONLY"
WARNING_BATCH_FIXTURE_MISSING = "BATCH_FIXTURE_MISSING"
WARNING_BATCH_COMPANY_FAILED = "BATCH_COMPANY_FAILED"
WARNING_BATCH_STOPPED_AFTER_COMPANY_ERROR = "BATCH_STOPPED_AFTER_COMPANY_ERROR"
WARNING_BATCH_NOT_RUN_AFTER_FAILURE = "BATCH_NOT_RUN_AFTER_FAILURE"
WARNING_BATCH_LIVE_FETCH_PLANNED = "BATCH_LIVE_FETCH_PLANNED"


@dataclass(frozen=True)
class BatchCompany:
    ticker: str
    company_name: str


@dataclass(frozen=True)
class FixturePaths:
    submissions_fixture: Path
    companyfacts_fixture: Path


@dataclass(frozen=True)
class BatchPlan:
    universe: str
    companies: tuple[BatchCompany, ...]
    dry_run: bool
    export_only: bool
    live_sec_fetch: bool
    network_access: bool
    api_level: str
    out_dir: Path
    db_path: Path


class BatchConfigError(ValueError):
    """Raised when a batch request would cross an explicit safety boundary."""


def generate_batch_plan(
    *,
    universe: str = AI_INFRA_CORE_UNIVERSE,
    companies: list[str] | tuple[str, ...] | None = None,
    out_dir: Path | str = DEFAULT_BATCH_OUTPUT_DIR,
    db_path: Path | str | None = None,
    dry_run: bool = False,
    export_only: bool = False,
    live_sec_fetch: bool = False,
    offline: bool = False,
    sec_user_agent: str | None = None,
) -> BatchPlan:
    """Validate batch inputs and produce a deterministic run plan."""

    if universe != AI_INFRA_CORE_UNIVERSE:
        raise BatchConfigError(f"Unsupported evidence batch universe: {universe}")
    if offline and live_sec_fetch:
        raise BatchConfigError("--offline blocks --live-sec-fetch.")
    if export_only and live_sec_fetch:
        raise BatchConfigError("--export-only cannot be combined with --live-sec-fetch.")
    if live_sec_fetch and not (sec_user_agent or "").strip():
        raise BatchConfigError("--live-sec-fetch requires --sec-user-agent.")

    company_map = {ticker: BatchCompany(ticker=ticker, company_name=name) for ticker, name in AI_INFRA_CORE_COMPANIES}
    requested = [ticker.upper() for ticker in companies] if companies else list(company_map)
    unknown = [ticker for ticker in requested if ticker not in company_map]
    if unknown:
        raise BatchConfigError(f"Unsupported ticker(s) for {universe}: {', '.join(unknown)}")
    if len(set(requested)) != len(requested):
        raise BatchConfigError("Duplicate tickers are not allowed in a batch request.")

    target = Path(out_dir)
    database_path = Path(db_path) if db_path is not None else target / DEFAULT_DB_PATH.name
    api_level = "Level 1" if live_sec_fetch else "Level 0"
    return BatchPlan(
        universe=universe,
        companies=tuple(company_map[ticker] for ticker in requested),
        dry_run=dry_run,
        export_only=export_only,
        live_sec_fetch=live_sec_fetch,
        network_access=live_sec_fetch and not dry_run and not export_only,
        api_level=api_level,
        out_dir=target,
        db_path=database_path,
    )


def run_batch(
    *,
    universe: str = AI_INFRA_CORE_UNIVERSE,
    companies: list[str] | tuple[str, ...] | None = None,
    out_dir: Path | str = DEFAULT_BATCH_OUTPUT_DIR,
    db_path: Path | str | None = None,
    dry_run: bool = False,
    offline: bool = False,
    export_only: bool = False,
    live_sec_fetch: bool = False,
    sec_user_agent: str | None = None,
    sec_cache_dir: Path | str = DEFAULT_SEC_CACHE_DIR,
    force_refresh: bool = False,
    continue_on_company_error: bool = False,
    fixture_paths: dict[str, FixturePaths] | None = None,
) -> dict[str, Any]:
    """Run a safe AI-infrastructure Evidence DB coverage batch."""

    plan = generate_batch_plan(
        universe=universe,
        companies=companies,
        out_dir=out_dir,
        db_path=db_path,
        dry_run=dry_run,
        export_only=export_only,
        live_sec_fetch=live_sec_fetch,
        offline=offline,
        sec_user_agent=sec_user_agent,
    )
    fixture_paths = {ticker.upper(): paths for ticker, paths in (fixture_paths or {}).items()}
    plan.out_dir.mkdir(parents=True, exist_ok=True)

    run_id = _run_id(plan)
    warnings: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    standard_outputs: dict[str, str] = {}

    if dry_run:
        warnings.append(_warning(WARNING_BATCH_DRY_RUN, "Dry run generated a batch plan without network access or imports."))
        if live_sec_fetch:
            warnings.append(_warning(WARNING_BATCH_LIVE_FETCH_PLANNED, "Live SEC fetch was planned but not executed during dry run."))
        summary_rows = [_summary_row(company, status="planned", output_dir=plan.out_dir) for company in plan.companies]
        manifest = _build_manifest(
            run_id=run_id,
            plan=plan,
            summary_rows=summary_rows,
            warnings=warnings,
            standard_manifest={},
            force_refresh=force_refresh,
            continue_on_company_error=continue_on_company_error,
        )
        outputs = _write_batch_outputs(plan.out_dir, manifest, warnings, summary_rows)
        return {"status": "planned", "run_id": run_id, "manifest": manifest, "outputs": outputs}

    if export_only:
        warnings.append(_warning(WARNING_BATCH_EXPORT_ONLY, "Export-only mode re-exported an existing local Evidence DB without network access."))
        standard_outputs = _export_existing_database(plan.db_path, plan.out_dir, plan)
        summary_rows = _summary_from_database(plan.db_path, plan.companies, plan.out_dir)
        manifest = _build_manifest(
            run_id=run_id,
            plan=plan,
            summary_rows=summary_rows,
            warnings=warnings,
            standard_manifest=_load_standard_manifest(plan.out_dir),
            force_refresh=force_refresh,
            continue_on_company_error=continue_on_company_error,
        )
        batch_outputs = _write_batch_outputs(plan.out_dir, manifest, warnings, summary_rows)
        return {"status": "exported", "run_id": run_id, "manifest": manifest, "outputs": {**standard_outputs, **batch_outputs}}

    stopped = False
    for company in plan.companies:
        if stopped:
            row = _summary_row(
                company,
                status="not_run",
                output_dir=plan.out_dir,
                warning_codes=[WARNING_BATCH_NOT_RUN_AFTER_FAILURE],
            )
            summary_rows.append(row)
            warnings.append(
                _warning(
                    WARNING_BATCH_NOT_RUN_AFTER_FAILURE,
                    f"{company.ticker} was not run because an earlier company failed and continuation was disabled.",
                    ticker=company.ticker,
                )
            )
            continue

        try:
            outputs = _run_company(
                company=company,
                plan=plan,
                fixture_paths=fixture_paths,
                sec_user_agent=sec_user_agent or "",
                sec_cache_dir=sec_cache_dir,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed per company.
            warning_code = WARNING_BATCH_FIXTURE_MISSING if isinstance(exc, FileNotFoundError) else WARNING_BATCH_COMPANY_FAILED
            row = _summary_row(
                company,
                status="failed",
                output_dir=plan.out_dir,
                warning_codes=[warning_code],
            )
            summary_rows.append(row)
            warnings.append(
                _warning(
                    warning_code,
                    f"{company.ticker} failed closed: {exc}",
                    ticker=company.ticker,
                )
            )
            if not continue_on_company_error:
                stopped = True
                warnings.append(
                    _warning(
                        WARNING_BATCH_STOPPED_AFTER_COMPANY_ERROR,
                        "Batch stopped after company failure because --continue-on-company-error was not supplied.",
                        ticker=company.ticker,
                    )
                )
            continue

        standard_outputs = {key: str(value) for key, value in outputs.items() if isinstance(value, str)}
        status = str(outputs.get("status") or "completed")
        warning_codes = _warning_codes_for_company_from_database(plan.db_path, company.ticker)
        if status != "completed":
            warning_codes.append(WARNING_BATCH_COMPANY_FAILED)
            warnings.append(
                _warning(
                    WARNING_BATCH_COMPANY_FAILED,
                    f"{company.ticker} failed closed during import.",
                    ticker=company.ticker,
                )
            )
            if not continue_on_company_error:
                stopped = True
                warnings.append(
                    _warning(
                        WARNING_BATCH_STOPPED_AFTER_COMPANY_ERROR,
                        "Batch stopped after company failure because --continue-on-company-error was not supplied.",
                        ticker=company.ticker,
                    )
                )
        summary_rows.append(
            _summary_row(
                company,
                status=status,
                filings_count=int(outputs.get("filings_count") or 0),
                facts_count=int(outputs.get("facts_count") or 0),
                warnings_count=int(outputs.get("warnings_count") or 0),
                newest_source_date=_newest_source_date(plan.out_dir, company.ticker),
                output_dir=plan.out_dir,
                warning_codes=warning_codes,
            )
        )

    if not standard_outputs:
        standard_outputs = _export_current_database(plan.db_path, plan.out_dir, plan)

    manifest = _build_manifest(
        run_id=run_id,
        plan=plan,
        summary_rows=summary_rows,
        warnings=warnings,
        standard_manifest=_load_standard_manifest(plan.out_dir),
        force_refresh=force_refresh,
        continue_on_company_error=continue_on_company_error,
    )
    batch_outputs = _write_batch_outputs(plan.out_dir, manifest, warnings, summary_rows)
    status = "completed" if not manifest["companies_failed"] and not stopped else "completed_with_failures"
    return {"status": status, "run_id": run_id, "manifest": manifest, "outputs": {**standard_outputs, **batch_outputs}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe batch SEC / IR Evidence DB imports for the AI infrastructure universe.")
    parser.add_argument("--universe", choices=[AI_INFRA_CORE_UNIVERSE], required=True)
    parser.add_argument("--companies", nargs="+")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_BATCH_OUTPUT_DIR)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--live-sec-fetch", action="store_true")
    parser.add_argument("--sec-user-agent")
    parser.add_argument("--sec-cache-dir", type=Path, default=DEFAULT_SEC_CACHE_DIR)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--continue-on-company-error", action="store_true")
    parser.add_argument("--fixture-dir", type=Path, help="Optional local fixture directory for tests and offline development.")
    args = parser.parse_args(argv)

    try:
        fixtures = _fixture_paths_from_dir(args.fixture_dir, args.companies) if args.fixture_dir else None
        result = run_batch(
            universe=args.universe,
            companies=args.companies,
            out_dir=args.out_dir,
            db_path=args.db,
            dry_run=args.dry_run,
            offline=args.offline,
            export_only=args.export_only,
            live_sec_fetch=args.live_sec_fetch,
            sec_user_agent=args.sec_user_agent,
            sec_cache_dir=args.sec_cache_dir,
            force_refresh=args.force_refresh,
            continue_on_company_error=args.continue_on_company_error,
            fixture_paths=fixtures,
        )
    except BatchConfigError as exc:
        parser.error(str(exc))
    except FileNotFoundError as exc:
        print(f"batch import failed closed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"status": result["status"], "run_id": result["run_id"], "outputs": result["outputs"]}, indent=2, sort_keys=True))
    return 0 if result["status"] in {"planned", "completed", "exported"} else 2


def _run_company(
    *,
    company: BatchCompany,
    plan: BatchPlan,
    fixture_paths: dict[str, FixturePaths],
    sec_user_agent: str,
    sec_cache_dir: Path | str,
    force_refresh: bool,
) -> dict[str, Any]:
    if plan.live_sec_fetch:
        return import_live_sec(
            ticker=company.ticker,
            company_name=company.company_name,
            user_agent=sec_user_agent,
            out_dir=plan.out_dir,
            db_path=plan.db_path,
            cache_dir=sec_cache_dir,
            force_refresh=force_refresh,
        )

    paths = fixture_paths.get(company.ticker)
    if paths is None:
        raise FileNotFoundError(f"Missing fixture paths for {company.ticker}.")
    if not paths.submissions_fixture.exists() or not paths.companyfacts_fixture.exists():
        raise FileNotFoundError(f"Missing fixture files for {company.ticker}.")
    return import_fixtures(
        submissions_fixture=paths.submissions_fixture,
        companyfacts_fixture=paths.companyfacts_fixture,
        ticker=company.ticker,
        company_name=company.company_name,
        out_dir=plan.out_dir,
        db_path=plan.db_path,
    )


def _export_current_database(db_path: Path, out_dir: Path, plan: BatchPlan) -> dict[str, str]:
    with EvidenceRepository(db_path) as repo:
        repo.commit()
        return export_all(
            repo,
            out_dir,
            manifest_context={
                "api_level": plan.api_level,
                "fixture_only": not plan.live_sec_fetch,
                "network_access": False,
                "live_sec_api": False,
            },
            report_filename="SEC_IR_EVIDENCE_DB_BATCH_EXPORT_REPORT.md",
        )


def _export_existing_database(db_path: Path, out_dir: Path, plan: BatchPlan) -> dict[str, str]:
    with EvidenceRepository(db_path, read_only=True) as repo:
        provenance = _source_provenance_from_repo(repo)
        return export_all(
            repo,
            out_dir,
            manifest_context={
                "api_level": provenance["source_api_level"] if provenance["source_api_level"] != "UNKNOWN" else plan.api_level,
                "fixture_only": provenance["source_fixture_only"] if provenance["source_fixture_only"] != "UNKNOWN" else not plan.live_sec_fetch,
                "network_access": False,
                "live_sec_api": provenance["source_live_sec_api"] if provenance["source_live_sec_api"] != "UNKNOWN" else False,
            },
            report_filename="SEC_IR_EVIDENCE_DB_BATCH_EXPORT_REPORT.md",
        )


def _summary_from_database(db_path: Path, companies: tuple[BatchCompany, ...], out_dir: Path) -> list[dict[str, Any]]:
    with EvidenceRepository(db_path, read_only=True) as repo:
        rows: list[dict[str, Any]] = []
        for company in companies:
            filings_count = _count_for_ticker(repo, "sec_filings", company.ticker)
            facts_count = _count_for_ticker(repo, "xbrl_facts", company.ticker)
            warnings_count = _warning_count_for_ticker(repo, company.ticker)
            status = "exported" if filings_count or facts_count else "missing_evidence"
            rows.append(
                _summary_row(
                    company,
                    status=status,
                    filings_count=filings_count,
                    facts_count=facts_count,
                    warnings_count=warnings_count,
                    newest_source_date=_newest_source_date_from_repo(repo, company.ticker),
                    output_dir=out_dir,
                    warning_codes=_warning_codes_for_company_from_repo(repo, company.ticker),
                )
            )
    return rows


def _count_for_ticker(repo: EvidenceRepository, table: str, ticker: str) -> int:
    rows = repo.fetch_all(
        f"""
        SELECT COUNT(*) AS count
        FROM {table} item
        JOIN companies c ON c.company_id = item.company_id
        WHERE c.ticker = ?
        """,
        (ticker,),
    )
    return int(rows[0]["count"]) if rows else 0


def _warning_count_for_ticker(repo: EvidenceRepository, ticker: str) -> int:
    rows = repo.fetch_all(
        """
        SELECT COUNT(*) AS count
        FROM ingestion_warnings iw
        JOIN ingestion_runs ir ON ir.run_id = iw.run_id
        WHERE ir.ticker = ?
        """,
        (ticker,),
    )
    return int(rows[0]["count"]) if rows else 0


def _newest_source_date_from_repo(repo: EvidenceRepository, ticker: str) -> str:
    rows = repo.fetch_all(
        """
        SELECT MAX(sd.source_date) AS newest_source_date
        FROM source_documents sd
        JOIN companies c ON c.company_id = sd.company_id
        WHERE c.ticker = ? AND sd.source_date != ''
        """,
        (ticker,),
    )
    return str(rows[0]["newest_source_date"] or "") if rows else ""


def _build_manifest(
    *,
    run_id: str,
    plan: BatchPlan,
    summary_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    standard_manifest: dict[str, Any],
    force_refresh: bool,
    continue_on_company_error: bool,
) -> dict[str, Any]:
    completed = [row["ticker"] for row in summary_rows if row["status"] in {"completed", "exported"}]
    failed = [row["ticker"] for row in summary_rows if row["status"] in {"failed", "missing_evidence"}]
    provenance = _source_provenance_from_manifest(standard_manifest)
    global_evidence_warning_codes = sorted(str(code) for code in (standard_manifest.get("warning_codes") or []))
    warning_codes = sorted({code for warning in warnings for code in [warning["code"]]} | _summary_warning_codes(summary_rows))
    return {
        "run_id": run_id,
        "generated_at": utc_now(),
        "universe": plan.universe,
        "companies_requested": [company.ticker for company in plan.companies],
        "companies_completed": completed,
        "companies_failed": failed,
        "api_level": provenance["source_api_level"],
        "fixture_only": provenance["source_fixture_only"],
        "network_access": plan.network_access,
        "live_sec_api": provenance["source_live_sec_api"],
        "source_api_level": provenance["source_api_level"],
        "source_fixture_only": provenance["source_fixture_only"],
        "source_live_sec_api": provenance["source_live_sec_api"],
        "cache_used": bool(standard_manifest.get("cache_used", False)),
        "force_refresh": force_refresh,
        "dry_run": plan.dry_run,
        "export_only": plan.export_only,
        "continue_on_company_error": continue_on_company_error,
        "per_company_output_status": summary_rows,
        "global_evidence_warning_codes": global_evidence_warning_codes,
        "warning_codes": warning_codes,
        "warnings": warnings,
        "standard_outputs": {
            "evidence_db": str(plan.db_path),
            "company_evidence_ledger": str(plan.out_dir / "company_evidence_ledger.csv"),
            "metric_history": str(plan.out_dir / "metric_history.csv"),
            "source_manifest": str(plan.out_dir / "source_manifest.json"),
            "ingestion_warnings": str(plan.out_dir / "ingestion_warnings.md"),
        },
        "no_portfolio_data": True,
        "no_broker_data": True,
        "no_client_data": True,
        "no_pm_recommendation_wiring": True,
        "no_llm": True,
        "no_yfinance": True,
    }


def _summary_warning_codes(summary_rows: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for row in summary_rows:
        codes.update(code for code in str(row.get("warning_codes") or "").split(";") if code)
    return codes


def _source_provenance_from_manifest(standard_manifest: dict[str, Any]) -> dict[str, Any]:
    sources = [source for source in standard_manifest.get("sources", []) if isinstance(source, dict)]
    api_levels = {
        str(source.get("source_level") or source.get("metadata", {}).get("api_level") or "").strip()
        for source in sources
        if str(source.get("source_level") or source.get("metadata", {}).get("api_level") or "").strip()
    }
    if not api_levels and standard_manifest.get("api_level"):
        api_levels.add(str(standard_manifest["api_level"]))

    fixture_values = {bool(source["fixture_only"]) for source in sources if "fixture_only" in source}
    live_values = {
        bool(source.get("metadata", {}).get("live_sec_api"))
        for source in sources
        if isinstance(source.get("metadata"), dict) and "live_sec_api" in source["metadata"]
    }
    if any(str(source.get("source_type") or "") == "SEC_EDGAR_PUBLIC_API" for source in sources):
        live_values.add(True)
    if not live_values and "live_sec_api" in standard_manifest and sources:
        live_values.add(bool(standard_manifest["live_sec_api"]))

    return {
        "source_api_level": _collapse_values(api_levels),
        "source_fixture_only": _collapse_values(fixture_values),
        "source_live_sec_api": _collapse_values(live_values),
    }


def _source_provenance_from_repo(repo: EvidenceRepository) -> dict[str, Any]:
    rows = repo.fetch_all(
        """
        SELECT source_type, fixture_only, metadata_json
        FROM source_documents
        """
    )
    api_levels: set[str] = set()
    fixture_values: set[bool] = set()
    live_values: set[bool] = set()
    for row in rows:
        metadata = _json_loads(str(row["metadata_json"] or "{}"))
        api_level = str(metadata.get("api_level") or "").strip()
        if api_level:
            api_levels.add(api_level)
        fixture_values.add(bool(row["fixture_only"]))
        if "live_sec_api" in metadata:
            live_values.add(bool(metadata["live_sec_api"]))
        if str(row["source_type"] or "") == "SEC_EDGAR_PUBLIC_API":
            live_values.add(True)
            api_levels.add("Level 1")
    return {
        "source_api_level": _collapse_values(api_levels),
        "source_fixture_only": _collapse_values(fixture_values),
        "source_live_sec_api": _collapse_values(live_values),
    }


def _collapse_values(values: set[Any]) -> Any:
    cleaned = {value for value in values if value != ""}
    if not cleaned:
        return "UNKNOWN"
    if len(cleaned) == 1:
        return next(iter(cleaned))
    if True in cleaned and False in cleaned:
        return "MIXED"
    if "Level 1" in cleaned:
        return "Level 1"
    return "MIXED"


def _write_batch_outputs(
    out_dir: Path,
    manifest: dict[str, Any],
    warnings: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
) -> dict[str, str]:
    manifest_path = out_dir / BATCH_MANIFEST_FILENAME
    warnings_path = out_dir / BATCH_WARNINGS_FILENAME
    summary_path = out_dir / COMPANY_RUN_SUMMARY_FILENAME

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_path.write_text(_warnings_markdown(manifest, warnings), encoding="utf-8")
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPANY_SUMMARY_FIELDS)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({field: row.get(field, "") for field in COMPANY_SUMMARY_FIELDS})

    return {
        "batch_manifest": str(manifest_path),
        "batch_warnings": str(warnings_path),
        "company_run_summary": str(summary_path),
    }


def _warnings_markdown(manifest: dict[str, Any], warnings: list[dict[str, Any]]) -> str:
    lines = [
        "# SEC / IR Evidence Batch Warnings",
        "",
        f"- Run id: `{manifest['run_id']}`",
        f"- Universe: `{manifest['universe']}`",
        f"- Live SEC API: `{str(manifest['live_sec_api']).lower()}`",
        "- Portfolio, broker, client, LLM, yfinance, and PM recommendation wiring: no.",
        "",
    ]
    if not warnings:
        lines.append("No batch warnings.")
        lines.append("")
        return "\n".join(lines)
    for warning in warnings:
        lines.append(f"- `{warning['code']}`: {warning['message']}")
        if warning.get("ticker"):
            lines.append(f"  - Ticker: `{warning['ticker']}`")
    lines.append("")
    return "\n".join(lines)


def _summary_row(
    company: BatchCompany,
    *,
    status: str,
    filings_count: int = 0,
    facts_count: int = 0,
    warnings_count: int = 0,
    newest_source_date: str = "",
    output_dir: Path | str = "",
    warning_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ticker": company.ticker,
        "company_name": company.company_name,
        "status": status,
        "filings_count": filings_count,
        "facts_count": facts_count,
        "warnings_count": warnings_count,
        "newest_source_date": newest_source_date,
        "output_dir": str(output_dir),
        "warning_codes": ";".join(sorted(set(warning_codes or []))),
    }


def _warning(code: str, message: str, *, ticker: str = "") -> dict[str, Any]:
    return {"code": code, "message": message, "ticker": ticker, "created_at": utc_now()}


def _warning_codes_for_company_from_database(db_path: Path, ticker: str) -> list[str]:
    with EvidenceRepository(db_path, read_only=True) as repo:
        return _warning_codes_for_company_from_repo(repo, ticker)


def _warning_codes_for_company_from_repo(repo: EvidenceRepository, ticker: str) -> list[str]:
    rows = repo.fetch_all(
        """
        SELECT DISTINCT iw.code
        FROM ingestion_warnings iw
        JOIN ingestion_runs ir ON ir.run_id = iw.run_id
        WHERE ir.ticker = ?
        ORDER BY iw.code
        """,
        (ticker,),
    )
    return [str(row["code"]) for row in rows]


def _newest_source_date(out_dir: Path, ticker: str) -> str:
    manifest = _load_standard_manifest(out_dir)
    sources = manifest.get("sources") or []
    dates = sorted(
        str(source.get("source_date") or "")
        for source in sources
        if isinstance(source, dict) and str(source.get("ticker") or "").upper() == ticker and source.get("source_date")
    )
    return dates[-1] if dates else ""


def _load_standard_manifest(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "source_manifest.json"
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fixture_paths_from_dir(fixture_dir: Path, companies: list[str] | None) -> dict[str, FixturePaths]:
    requested = [ticker.upper() for ticker in companies] if companies else [ticker for ticker, _ in AI_INFRA_CORE_COMPANIES]
    return {
        ticker: FixturePaths(
            submissions_fixture=fixture_dir / f"{ticker}_submissions_sample.json",
            companyfacts_fixture=fixture_dir / f"{ticker}_companyfacts_sample.json",
        )
        for ticker in requested
    }


def _run_id(plan: BatchPlan) -> str:
    tickers = "_".join(company.ticker for company in plan.companies)
    return f"batch_{plan.universe}_{tickers}_{utc_now().replace(':', '').replace('+', 'Z')}"

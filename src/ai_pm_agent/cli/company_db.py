"""CLI for importing and inspecting the local company research database."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ai_pm_agent.artifacts.importer import CompanyDbImporter, ImportSummary
from ai_pm_agent.company_db.repository import CompanyResearchRepository, DecisionFilters


DEFAULT_OUTPUTS = Path("outputs")
DEFAULT_DB = Path("data") / "company_db" / "company_research.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import and query AI PM Agent artifacts in SQLite.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import research run artifacts.")
    add_common_import_args(import_parser)
    import_parser.add_argument("--dry-run", action="store_true", help="Scan artifacts without writing DB rows.")
    import_parser.add_argument("--verbose", action="store_true", help="Print per-run warning details.")

    validate_parser = subparsers.add_parser("validate", help="Dry-run artifact discovery and parse validation.")
    add_common_import_args(validate_parser)
    validate_parser.add_argument("--verbose", action="store_true", help="Print per-run warning details.")

    stats_parser = subparsers.add_parser("stats", help="Summarize imported database counts.")
    add_db_arg(stats_parser)

    list_parser = subparsers.add_parser("list", help="List latest imported decisions.")
    add_query_args(list_parser)

    latest_parser = subparsers.add_parser("latest", help="Show the latest decision table.")
    add_query_args(latest_parser)

    show_parser = subparsers.add_parser("show", help="Show imported decisions for a ticker.")
    show_parser.add_argument("ticker_arg", nargs="?", help="Ticker to inspect.")
    show_parser.add_argument("--ticker", help="Ticker to inspect.")
    add_db_arg(show_parser)
    show_parser.add_argument("--limit", type=int, default=10, help="Maximum rows to display.")

    history_parser = subparsers.add_parser("history", help="Show decision history for a ticker.")
    history_parser.add_argument("ticker_arg", nargs="?", help="Ticker to inspect.")
    history_parser.add_argument("--ticker", help="Ticker to inspect.")
    add_db_arg(history_parser)
    history_parser.add_argument("--limit", type=int, default=50, help="Maximum rows to display.")

    rank_parser = subparsers.add_parser("rank", help="Rank latest decisions by score.")
    add_query_args(rank_parser, default_sort="chokepoint_score")

    warnings_parser = subparsers.add_parser("warnings", help="List import warnings.")
    add_db_arg(warnings_parser)
    warnings_parser.add_argument("--ticker", help="Filter warnings by ticker.")
    warnings_parser.add_argument("--warning-type", help="Filter warnings by warning type.")
    warnings_parser.add_argument("--limit", type=int, default=50, help="Maximum rows to display.")

    stale_parser = subparsers.add_parser("stale", help="List stale or incomplete company records.")
    add_db_arg(stale_parser)
    stale_parser.add_argument("--limit", type=int, default=100, help="Maximum rows to display.")

    export_parser = subparsers.add_parser("export-csv", help="Export query results to CSV.")
    add_query_args(export_parser)
    export_parser.add_argument(
        "--type",
        choices=("latest_decisions", "chokepoint_ranking", "stale", "warnings"),
        default="latest_decisions",
        help="Export view type.",
    )
    export_parser.add_argument("--out", required=True, help="CSV output path.")

    return parser


def add_common_import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--outputs", default=str(DEFAULT_OUTPUTS), help="Outputs directory to scan.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum run folders to scan.")


def add_db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path.")


def add_query_args(parser: argparse.ArgumentParser, default_sort: str = "latest_run_date") -> None:
    add_db_arg(parser)
    parser.add_argument("--ticker", help="Filter by ticker.")
    parser.add_argument("--market", help="Filter by market.")
    parser.add_argument("--action", help="Filter by action.")
    parser.add_argument("--rating", help="Filter by rating.")
    parser.add_argument("--min-chokepoint-score", type=float, help="Minimum chokepoint score.")
    parser.add_argument("--max-chokepoint-score", type=float, help="Maximum chokepoint score.")
    parser.add_argument("--min-pm-score", type=float, help="Minimum PM score.")
    parser.add_argument("--max-pm-score", type=float, help="Maximum PM score.")
    parser.add_argument("--has-warnings", action="store_true", help="Only include rows with warnings.")
    parser.add_argument("--missing-evidence", action="store_true", help="Only include rows missing evidence rows.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows to display.")
    parser.add_argument("--sort", default=default_sort, help="Sort field.")
    parser.add_argument("--desc", action="store_true", default=None, help="Sort descending.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "import":
        importer = CompanyDbImporter(args.outputs, args.db, args.limit)
        summary = importer.import_outputs(dry_run=args.dry_run)
        print_summary(summary, verbose=args.verbose)
        return 0

    if args.command == "validate":
        importer = CompanyDbImporter(args.outputs, args.db, args.limit)
        summary = importer.import_outputs(dry_run=True)
        print_summary(summary, verbose=args.verbose)
        return 0 if summary.discovered else 2

    if args.command == "stats":
        with CompanyResearchRepository(args.db) as repo:
            print_stats(repo.summarize_database())
        return 0

    if args.command in {"list", "latest"}:
        with CompanyResearchRepository(args.db) as repo:
            rows = repo.filter_decisions(
                filters=filters_from_args(args),
                limit=args.limit,
                sort=args.sort,
                desc=desc_from_args(args),
            )
            print_latest_rows(rows)
        return 0

    if args.command == "show":
        ticker = required_ticker(args)
        with CompanyResearchRepository(args.db) as repo:
            rows = repo.get_runs_for_ticker(ticker, limit=args.limit)
            print_history_rows(rows, include_judgment=True)
        return 0 if rows else 1

    if args.command == "history":
        ticker = required_ticker(args)
        with CompanyResearchRepository(args.db) as repo:
            rows = repo.compare_ticker_history(ticker, limit=args.limit)
            print_history_rows(rows)
        return 0 if rows else 1

    if args.command == "rank":
        with CompanyResearchRepository(args.db) as repo:
            rows = repo.filter_decisions(
                filters=filters_from_args(args),
                limit=args.limit,
                sort=args.sort,
                desc=desc_from_args(args),
            )
            print_rank_rows(rows)
        return 0

    if args.command == "warnings":
        with CompanyResearchRepository(args.db) as repo:
            rows = repo.list_import_warnings(
                ticker=args.ticker,
                warning_type=args.warning_type,
                limit=args.limit,
            )
            print_warning_rows(rows)
        return 0

    if args.command == "stale":
        with CompanyResearchRepository(args.db) as repo:
            print_stale_rows(repo.list_stale_or_incomplete_companies(limit=args.limit))
        return 0

    if args.command == "export-csv":
        with CompanyResearchRepository(args.db) as repo:
            rows, fields = export_rows(repo, args)
        write_csv(Path(args.out), rows, fields)
        print(f"exported rows={len(rows)} out={args.out}")
        return 0

    return 2


def print_summary(summary: ImportSummary, verbose: bool = False) -> None:
    print(
        "summary "
        f"dry_run={summary.dry_run} "
        f"discovered={summary.discovered} "
        f"imported={summary.imported} "
        f"would_import={summary.would_import} "
        f"skipped={summary.skipped} "
        f"warnings={summary.warnings} "
        f"outputs={summary.outputs_dir} "
        f"db={summary.db_path}"
    )
    if not verbose:
        return
    for result in summary.results:
        print(
            "run "
            f"status={result.status} "
            f"files={result.imported_files} "
            f"evidence={result.evidence_items} "
            f"facts={result.facts} "
            f"warnings={len(result.warnings)} "
            f"path={result.artifact_dir}"
        )
        for warning in result.warnings:
            print(
                "warning "
                f"type={warning.warning_type} "
                f"path={warning.artifact_path or ''} "
                f"message={warning.message}"
            )


def print_latest_rows(rows: list[object]) -> None:
    fields = [
        "ticker",
        "company",
        "market",
        "action",
        "rating",
        "pm_score",
        "chokepoint_score",
        "confidence",
        "latest_run_date",
        "warning_count",
    ]
    aliases = {"company": "company_name"}
    print_rows(rows, fields, aliases=aliases, empty_message="No imported decisions found.")


def print_rank_rows(rows: list[object]) -> None:
    fields = [
        "ticker",
        "company",
        "chokepoint_score",
        "evidence_level",
        "action",
        "rating",
        "latest_run_date",
    ]
    aliases = {"company": "company_name"}
    print_rows(rows, fields, aliases=aliases, empty_message="No ranked decisions found.")


def print_history_rows(rows: list[object], include_judgment: bool = False) -> None:
    fields = [
        "run_date",
        "action",
        "rating",
        "pm_score",
        "chokepoint_score",
        "suggested_position",
        "artifact_path",
    ]
    aliases = {
        "run_date": "latest_run_date",
        "suggested_position": "suggested_position_pct",
        "artifact_path": "artifact_dir",
    }
    print_rows(rows, fields, aliases=aliases, empty_message="No history found.")
    if include_judgment:
        for row in rows:
            if row["final_pm_judgment"]:
                print(f"  judgment: {clean_cell(row['final_pm_judgment'], max_len=220)}")


def print_stale_rows(rows: list[object]) -> None:
    fields = [
        "ticker",
        "company",
        "latest_run_date",
        "missing_artifacts",
        "warning_count",
        "has_market_snapshot",
        "has_pm_decision",
        "has_chokepoint_assessment",
    ]
    aliases = {"company": "company_name"}
    print_rows(rows, fields, aliases=aliases, empty_message="No incomplete company records found.")


def print_warning_rows(rows: list[object]) -> None:
    fields = ["warning_type", "ticker", "company", "latest_run_date", "message", "artifact_path"]
    aliases = {"company": "company_name"}
    print_rows(rows, fields, aliases=aliases, empty_message="No import warnings found.")


def print_stats(summary: dict[str, object]) -> None:
    counts = summary["counts"]
    warning_types = summary["warning_types"]
    print("counts")
    for key, value in counts.items():
        print(f"{key}={value}")
    print("warning_types")
    if warning_types:
        for key, value in warning_types.items():
            print(f"{key}={value}")
    else:
        print("none=0")


def print_rows(
    rows: list[object],
    fields: list[str],
    aliases: dict[str, str] | None = None,
    empty_message: str = "No rows found.",
) -> None:
    if not rows:
        print(empty_message)
        return
    aliases = aliases or {}
    print(" | ".join(fields))
    print(" | ".join("-" * len(header) for header in fields))
    for row in rows:
        values = []
        for field in fields:
            values.append(clean_cell(row[aliases.get(field, field)]))
        print(" | ".join(values))


def filters_from_args(args: argparse.Namespace) -> DecisionFilters:
    return DecisionFilters(
        ticker=args.ticker,
        market=args.market,
        action=args.action,
        rating=args.rating,
        min_chokepoint_score=args.min_chokepoint_score,
        max_chokepoint_score=args.max_chokepoint_score,
        min_pm_score=args.min_pm_score,
        max_pm_score=args.max_pm_score,
        has_warnings=True if args.has_warnings else None,
        missing_evidence=True if args.missing_evidence else None,
    )


def desc_from_args(args: argparse.Namespace) -> bool:
    return True if args.desc is None else bool(args.desc)


def required_ticker(args: argparse.Namespace) -> str:
    ticker = args.ticker or args.ticker_arg
    if not ticker:
        raise SystemExit("ticker is required")
    return ticker


def export_rows(
    repo: CompanyResearchRepository,
    args: argparse.Namespace,
) -> tuple[list[object], list[str]]:
    export_type = args.type
    if export_type == "chokepoint_ranking":
        rows = repo.filter_decisions(
            filters=filters_from_args(args),
            limit=args.limit,
            sort="chokepoint_score",
            desc=desc_from_args(args),
        )
        fields = [
            "ticker",
            "company_name",
            "chokepoint_score",
            "evidence_level",
            "action",
            "rating",
            "latest_run_date",
        ]
        return rows, fields
    if export_type == "stale":
        rows = repo.list_stale_or_incomplete_companies(limit=args.limit)
        fields = [
            "ticker",
            "company_name",
            "latest_run_date",
            "missing_artifacts",
            "warning_count",
            "has_market_snapshot",
            "has_pm_decision",
            "has_chokepoint_assessment",
        ]
        return rows, fields
    if export_type == "warnings":
        rows = repo.list_import_warnings(limit=args.limit, ticker=args.ticker)
        fields = ["warning_type", "ticker", "company_name", "latest_run_date", "message", "artifact_path"]
        return rows, fields
    rows = repo.filter_decisions(
        filters=filters_from_args(args),
        limit=args.limit,
        sort=args.sort,
        desc=desc_from_args(args),
    )
    fields = [
        "ticker",
        "company_name",
        "market",
        "action",
        "rating",
        "pm_score",
        "chokepoint_score",
        "confidence",
        "latest_run_date",
        "warning_count",
    ]
    return rows, fields


def write_csv(path: Path, rows: list[object], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def clean_cell(value: object, max_len: int = 48) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("|", "/").strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


if __name__ == "__main__":
    sys.exit(main())

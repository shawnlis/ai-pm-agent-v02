"""CLI for offline company DB Markdown and CSV reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.reports.company_dossier import CompanyDossierGenerator
from ai_pm_agent.reports.markdown import write_csv, write_text
from ai_pm_agent.reports.watchlist_reports import ReportOutput, WatchlistReportGenerator


DEFAULT_DB = Path("data") / "company_db" / "company_research.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate offline company DB reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dossier = subparsers.add_parser("dossier", help="Generate one company dossier.")
    add_db_arg(dossier)
    dossier.add_argument("--ticker", required=True, help="Ticker to report.")
    dossier.add_argument("--out", required=True, help="Markdown output path.")

    batch = subparsers.add_parser("dossier-batch", help="Generate dossiers for comma-separated tickers.")
    add_db_arg(batch)
    batch.add_argument("--tickers", required=True, help="Comma-separated tickers.")
    batch.add_argument("--out-dir", required=True, help="Directory for Markdown dossier files.")

    top = subparsers.add_parser("top-chokepoints", help="Generate top chokepoint report.")
    add_report_args(top, default_csv="reports/exports/top_chokepoints.csv")

    latest = subparsers.add_parser("latest-decisions", help="Generate latest decisions report.")
    add_report_args(latest, default_csv="reports/exports/latest_decisions.csv", default_limit=50)

    stale = subparsers.add_parser("stale", help="Generate stale/incomplete data report.")
    add_report_args(stale, default_csv="reports/exports/stale_companies.csv", default_limit=200)

    warnings = subparsers.add_parser("warnings", help="Generate warning summary report.")
    add_report_args(warnings, default_csv="reports/exports/warning_summary.csv", default_limit=500)

    changes = subparsers.add_parser("decision-changes", help="Generate decision-change report.")
    add_report_args(changes, default_csv="reports/exports/decision_changes.csv", default_limit=200)

    return parser


def add_db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path.")


def add_report_args(
    parser: argparse.ArgumentParser,
    default_csv: str,
    default_limit: int = 25,
) -> None:
    add_db_arg(parser)
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum rows to include.")
    parser.add_argument("--out", required=True, help="Markdown output path.")
    parser.add_argument("--csv-out", default=default_csv, help="CSV table output path.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "dossier":
        with CompanyResearchRepository(args.db, read_only=True) as repo:
            markdown = CompanyDossierGenerator(repo).generate(args.ticker)
        write_text(args.out, markdown)
        print(f"generated dossier ticker={args.ticker.upper()} out={args.out}")
        return 0

    if args.command == "dossier-batch":
        tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
        out_dir = Path(args.out_dir)
        generated = []
        with CompanyResearchRepository(args.db, read_only=True) as repo:
            generator = CompanyDossierGenerator(repo)
            for ticker in tickers:
                path = out_dir / f"{ticker.replace('.', '_')}.md"
                write_text(path, generator.generate(ticker))
                generated.append(str(path))
        print(f"generated dossiers count={len(generated)} out_dir={args.out_dir}")
        for path in generated:
            print(path)
        return 0

    with CompanyResearchRepository(args.db, read_only=True) as repo:
        generator = WatchlistReportGenerator(repo)
        output = build_report_output(generator, args)
    write_text(args.out, output.markdown)
    write_csv(args.csv_out, output.csv_rows, output.csv_fields)
    print(f"generated report command={args.command} out={args.out} csv={args.csv_out}")
    return 0


def build_report_output(generator: WatchlistReportGenerator, args: argparse.Namespace) -> ReportOutput:
    if args.command == "top-chokepoints":
        return generator.top_chokepoints(limit=args.limit)
    if args.command == "latest-decisions":
        return generator.latest_decisions(limit=args.limit)
    if args.command == "stale":
        return generator.stale(limit=args.limit)
    if args.command == "warnings":
        return generator.warnings(limit=args.limit)
    if args.command == "decision-changes":
        return generator.decision_changes(limit=args.limit)
    raise SystemExit(f"Unsupported report command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())

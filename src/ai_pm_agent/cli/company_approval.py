"""CLI for offline refresh approval packet generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_pm_agent.approval.approved_commands import write_approved_command_outputs
from ai_pm_agent.approval.manifest import summarize_manifest, write_manifest
from ai_pm_agent.approval.packet import ApprovalPacketGenerator, ApprovalPacketOptions, explain_packet_text
from ai_pm_agent.approval.runbook import ManualRunbookGenerator
from ai_pm_agent.approval.validator import (
    ApprovalManifestValidator,
    render_dry_run_report,
    write_validation_outputs,
)
from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.refresh.queues import QUEUE_ORDER
from ai_pm_agent.reports.markdown import write_text


DEFAULT_DB = Path("data") / "company_db" / "company_research.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build offline review-only refresh approval packets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a filtered approval packet.")
    add_build_args(build)
    build.add_argument("--refresh-csv", help="Optional refresh CSV path to reference, not parse.")

    urgent = subparsers.add_parser("build-urgent", help="Build an urgent_refresh approval packet.")
    add_build_args(urgent, default_limit=None)

    high = subparsers.add_parser("build-high-priority", help="Build a high_priority approval packet.")
    add_build_args(high, default_limit=None)

    explain = subparsers.add_parser("explain-packet", help="Explain an approval manifest.")
    add_db_arg(explain)
    explain.add_argument("--manifest", required=True, help="Approval manifest CSV path.")

    validate = subparsers.add_parser("validate", help="Validate a manually edited approval manifest.")
    add_db_arg(validate)
    validate.add_argument("--manifest", required=True, help="Approval manifest CSV path.")
    validate.add_argument("--out", required=True, help="Markdown validation report output path.")
    validate.add_argument("--csv", required=True, help="Validation CSV output path.")
    validate.add_argument(
        "--include-not-approved",
        action="store_true",
        help="Include not-approved rows in the Markdown report.",
    )

    extract = subparsers.add_parser("extract-approved", help="Extract validated approved command templates.")
    add_db_arg(extract)
    extract.add_argument("--manifest", required=True, help="Approval manifest CSV path.")
    extract.add_argument("--commands-out", required=True, help="Approved command template output path.")
    extract.add_argument("--manifest-out", required=True, help="Validated manifest CSV output path.")
    extract.add_argument("--validation-out", required=True, help="Markdown validation report output path.")
    extract.add_argument(
        "--include-not-approved",
        action="store_true",
        help="Include not-approved rows in the Markdown validation report.",
    )

    dry_run = subparsers.add_parser(
        "dry-run-approved",
        help="Write what approved commands would be included without executing anything.",
    )
    add_db_arg(dry_run)
    dry_run.add_argument("--manifest", required=True, help="Approval manifest CSV path.")
    dry_run.add_argument("--out", required=True, help="Dry-run Markdown output path.")

    runbook = subparsers.add_parser("build-runbook", help="Build a manual execution runbook without executing commands.")
    add_db_arg(runbook)
    runbook.add_argument("--validated-manifest", required=True, help="Validated manifest CSV path.")
    runbook.add_argument("--commands", required=True, help="Approved commands text file path.")
    runbook.add_argument("--out", required=True, help="Manual runbook Markdown output path.")
    runbook.add_argument("--csv", required=True, help="Manual runbook steps CSV output path.")
    runbook.add_argument("--batch-size", type=int, default=5, help="Number of commands per batch.")

    return parser


def add_db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path.")


def add_build_args(parser: argparse.ArgumentParser, default_limit: int | None = 25) -> None:
    add_db_arg(parser)
    parser.add_argument("--queue", action="append", choices=QUEUE_ORDER, help="Queue filter. Can be repeated.")
    parser.add_argument("--min-score", type=float, help="Minimum refresh score.")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum candidates to include.")
    parser.add_argument("--ticker", action="append", help="Ticker filter. Can be repeated.")
    parser.add_argument("--tickers", help="Comma-separated ticker filters.")
    parser.add_argument("--include-monitor-only", action="store_true", help="Include monitor_only rows in default build.")
    parser.add_argument(
        "--exclude-no-refresh-needed",
        action="store_true",
        help="Exclude no_refresh_needed rows. This is the default for approval packets.",
    )
    parser.add_argument("--out", required=True, help="Markdown packet output path.")
    parser.add_argument("--manifest", required=True, help="Approval manifest CSV output path.")
    parser.add_argument("--commands-out", help="Manual command bundle output path.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "explain-packet":
        with CompanyResearchRepository(args.db, read_only=True):
            text = explain_packet_text(summarize_manifest(args.manifest), args.db)
        print(text)
        return 0

    if args.command in {"validate", "extract-approved", "dry-run-approved"}:
        with CompanyResearchRepository(args.db, read_only=True) as repo:
            result = ApprovalManifestValidator(repo).validate(args.manifest)

        if args.command == "validate":
            write_validation_outputs(
                result,
                markdown_path=args.out,
                csv_path=args.csv,
                include_not_approved=args.include_not_approved,
            )
            print(
                "validated approval_manifest "
                f"rows={result.total_rows} valid_approved={len(result.valid_approved_rows)} "
                f"invalid_approved={len(result.invalid_approved_rows)} "
                f"ambiguous={len(result.ambiguous_rows)} out={args.out} csv={args.csv}"
            )
            return 0

        if args.command == "extract-approved":
            write_approved_command_outputs(
                result,
                commands_out=args.commands_out,
                manifest_out=args.manifest_out,
                validation_out=args.validation_out,
                include_not_approved=args.include_not_approved,
            )
            print(
                "extracted approved_commands "
                f"valid_approved={len(result.valid_approved_rows)} "
                f"invalid_approved={len(result.invalid_approved_rows)} "
                f"ambiguous={len(result.ambiguous_rows)} "
                f"commands={args.commands_out} manifest={args.manifest_out} "
                f"validation={args.validation_out}"
            )
            return 0

        if args.command == "dry-run-approved":
            write_text(args.out, render_dry_run_report(result))
            print(
                "generated approved_dry_run "
                f"valid_approved={len(result.valid_approved_rows)} "
                f"invalid_approved={len(result.invalid_approved_rows)} "
                f"ambiguous={len(result.ambiguous_rows)} out={args.out}"
            )
            return 0

    if args.command == "build-runbook":
        with CompanyResearchRepository(args.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).write(
                validated_manifest_path=args.validated_manifest,
                approved_commands_path=args.commands,
                markdown_out=args.out,
                csv_out=args.csv,
                batch_size=args.batch_size,
            )
        print(
            "generated manual_runbook "
            f"valid_approved={len(result.valid_approved_rows)} "
            f"batches={len(result.batches)} commands={len(result.csv_rows)} "
            f"out={args.out} csv={args.csv}"
        )
        return 0

    queues = tuple(args.queue or ())
    if args.command == "build-urgent":
        queues = ("urgent_refresh",)
    elif args.command == "build-high-priority":
        queues = ("high_priority",)

    tickers = _ticker_filters(args.ticker, args.tickers)
    options = ApprovalPacketOptions(
        queues=queues,
        min_score=args.min_score,
        limit=args.limit,
        tickers=tickers,
        include_monitor_only=args.include_monitor_only,
        exclude_no_refresh_needed=True,
        refresh_csv=getattr(args, "refresh_csv", None),
    )

    with CompanyResearchRepository(args.db, read_only=True) as repo:
        result = ApprovalPacketGenerator(repo).build(options)

    write_text(args.out, result.markdown)
    write_manifest(args.manifest, result.manifest_rows)
    commands_out = args.commands_out or _default_commands_path(args.out)
    write_text(commands_out, result.command_bundle)
    print(
        "generated approval_packet "
        f"candidates={len(result.selected_candidates)} out={args.out} "
        f"manifest={args.manifest} commands={commands_out}"
    )
    return 0


def _ticker_filters(repeated: list[str] | None, comma_text: str | None) -> tuple[str, ...]:
    values: list[str] = []
    for ticker in repeated or []:
        values.append(ticker)
    if comma_text:
        values.extend(comma_text.split(","))
    return tuple(ticker.strip().upper() for ticker in values if ticker.strip())


def _default_commands_path(out_path: str) -> str:
    target = Path(out_path)
    return str(target.with_name(target.stem + "_manual_rerun_commands.txt"))


if __name__ == "__main__":
    sys.exit(main())

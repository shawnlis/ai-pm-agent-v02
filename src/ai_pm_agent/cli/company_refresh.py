"""CLI for offline refresh-candidate planning."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.refresh.planner import CSV_FIELDS, RefreshPlanner, candidates_to_csv_rows
from ai_pm_agent.refresh.queues import QUEUE_ORDER
from ai_pm_agent.reports.markdown import write_csv, write_text


DEFAULT_DB = Path("data") / "company_db" / "company_research.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan offline company research refresh queues.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stats = subparsers.add_parser("stats", help="Print refresh queue counts.")
    add_db_arg(stats)

    plan = subparsers.add_parser("plan", help="Generate the full refresh plan.")
    add_db_arg(plan)
    plan.add_argument("--out", required=True, help="Markdown output path.")
    plan.add_argument("--csv", required=True, help="CSV output path.")
    plan.add_argument("--include-all", action="store_true", help="Do not truncate monitor-only rows.")

    queue = subparsers.add_parser("queue", help="Generate one queue report.")
    add_db_arg(queue)
    queue.add_argument("--queue", required=True, choices=QUEUE_ORDER, help="Queue to export.")
    queue.add_argument("--out", required=True, help="Markdown output path.")
    queue.add_argument("--csv", required=True, help="CSV output path.")

    explain = subparsers.add_parser("explain", help="Explain one ticker refresh score.")
    add_db_arg(explain)
    explain.add_argument("--ticker", required=True, help="Ticker to explain.")

    return parser


def add_db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    with CompanyResearchRepository(args.db, read_only=True) as repo:
        planner = RefreshPlanner(repo)
        plan = planner.build_plan()

        if args.command == "stats":
            print_stats(plan)
            return 0

        if args.command == "plan":
            write_text(args.out, planner.render_plan_markdown(plan, include_all=args.include_all))
            write_csv(args.csv, candidates_to_csv_rows(plan.candidates), CSV_FIELDS)
            print(f"generated refresh_plan out={args.out} csv={args.csv}")
            return 0

        if args.command == "queue":
            candidates = [candidate for candidate in plan.candidates if candidate.queue == args.queue]
            write_text(args.out, planner.render_queue_markdown(plan, args.queue))
            write_csv(args.csv, candidates_to_csv_rows(candidates), CSV_FIELDS)
            print(f"generated refresh_queue queue={args.queue} rows={len(candidates)} out={args.out} csv={args.csv}")
            return 0

        if args.command == "explain":
            print(planner.render_explain_text(planner.explain(args.ticker), args.ticker))
            return 0

    return 2


def print_stats(plan: object) -> None:
    print(f"companies_evaluated={plan.companies_evaluated}")
    for queue, count in plan.queue_counts.items():
        print(f"{queue}={count}")
    print("top_candidates=" + ", ".join(candidate.ticker for candidate in plan.candidates[:10]))


if __name__ == "__main__":
    sys.exit(main())

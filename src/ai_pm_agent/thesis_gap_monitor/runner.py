"""Runner for the AI infrastructure thesis-gap monitor."""

from __future__ import annotations

import argparse
from datetime import date
import json
import sys
from pathlib import Path
from typing import Any

from .evidence_reader import MissingEvidenceInputError, load_from_paths
from .gap_rules import evaluate_gaps
from .models import DEFAULT_COMPANIES
from .report_writer import write_outputs


def run_monitor(
    *,
    evidence_dir: Path | str | None = None,
    ledger_csv: Path | str | None = None,
    metric_history_csv: Path | str | None = None,
    source_manifest_json: Path | str | None = None,
    warnings_md: Path | str | None = None,
    evidence_db_sqlite: Path | str | None = None,
    out_dir: Path | str | None = None,
    tickers: list[str] | None = None,
    as_of_date: date | None = None,
    stale_days: int = 548,
) -> dict[str, Any]:
    bundle = load_from_paths(
        evidence_dir=evidence_dir,
        ledger_csv=ledger_csv,
        metric_history_csv=metric_history_csv,
        source_manifest_json=source_manifest_json,
        warnings_md=warnings_md,
        evidence_db_sqlite=evidence_db_sqlite,
    )
    result = evaluate_gaps(
        bundle,
        companies=tickers or DEFAULT_COMPANIES,
        as_of_date=as_of_date,
        stale_days=stale_days,
    )
    outputs = write_outputs(result, out_dir=out_dir)
    return {
        "outputs": outputs,
        "status_counts": result.status_counts,
        "warning_codes": list(result.warning_codes),
        "manifest_summary": result.manifest_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AI infrastructure thesis-gap monitor v2.")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--ledger-csv", type=Path)
    parser.add_argument("--metric-history-csv", type=Path)
    parser.add_argument("--source-manifest-json", type=Path)
    parser.add_argument("--warnings-md", type=Path)
    parser.add_argument("--evidence-db-sqlite", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_COMPANIES)
    parser.add_argument("--as-of-date", help="YYYY-MM-DD date for freshness checks.")
    parser.add_argument("--stale-days", type=int, default=548)
    parser.add_argument("--offline", action="store_true", help="Accepted for explicit offline runs; network is never used.")
    args = parser.parse_args(argv)

    try:
        as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    except ValueError:
        print("--as-of-date must use YYYY-MM-DD format.", file=sys.stderr)
        return 2

    try:
        summary = run_monitor(
            evidence_dir=args.evidence_dir,
            ledger_csv=args.ledger_csv,
            metric_history_csv=args.metric_history_csv,
            source_manifest_json=args.source_manifest_json,
            warnings_md=args.warnings_md,
            evidence_db_sqlite=args.evidence_db_sqlite,
            out_dir=args.out_dir,
            tickers=args.tickers,
            as_of_date=as_of,
            stale_days=args.stale_days,
        )
    except MissingEvidenceInputError as exc:
        print(f"Evidence input error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0

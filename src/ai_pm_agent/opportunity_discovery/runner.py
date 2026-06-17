"""Runner and CLI for AI infrastructure opportunity discovery."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

from .exports import write_outputs
from .loader import MissingOpportunityInputError, load_from_paths
from .scoring import score_bundle


def run_discovery(
    *,
    evidence_dir: Path | str,
    monitor_dir: Path | str,
    prior_monitor_dir: Path | str | None = None,
    prior_scorecard_json: Path | str | None = None,
    prior_candidates_csv: Path | str | None = None,
    risk_summary_path: Path | str | None = None,
    out_dir: Path | str | None = None,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    bundle = load_from_paths(
        evidence_dir=evidence_dir,
        monitor_dir=monitor_dir,
        prior_monitor_dir=prior_monitor_dir,
        prior_scorecard_json=prior_scorecard_json,
        prior_candidates_csv=prior_candidates_csv,
        risk_summary_path=risk_summary_path,
    )
    result = score_bundle(bundle, as_of_date=as_of_date)
    outputs = write_outputs(result, out_dir=out_dir)
    return {
        "outputs": outputs,
        "status_counts": result.status_counts,
        "warning_codes": list(result.warning_codes),
        "candidates": [candidate.as_row() for candidate in result.candidates],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI infrastructure opportunity discovery v0.1.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--monitor-dir", type=Path, required=True)
    parser.add_argument("--prior-monitor-dir", type=Path)
    parser.add_argument("--prior-scorecard-json", type=Path)
    parser.add_argument("--prior-candidates-csv", type=Path)
    parser.add_argument("--risk-summary-path", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--as-of-date", help="YYYY-MM-DD date recorded for deterministic runs.")
    parser.add_argument("--offline", action="store_true", help="Accepted for explicit offline runs; network is never used.")
    args = parser.parse_args(argv)

    try:
        as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    except ValueError:
        print("--as-of-date must use YYYY-MM-DD format.", file=sys.stderr)
        return 2

    try:
        summary = run_discovery(
            evidence_dir=args.evidence_dir,
            monitor_dir=args.monitor_dir,
            prior_monitor_dir=args.prior_monitor_dir,
            prior_scorecard_json=args.prior_scorecard_json,
            prior_candidates_csv=args.prior_candidates_csv,
            risk_summary_path=args.risk_summary_path,
            out_dir=args.out_dir,
            as_of_date=as_of,
        )
    except MissingOpportunityInputError as exc:
        print(f"Opportunity discovery failed closed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0

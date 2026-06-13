"""Offline Portfolio Risk Cockpit runner."""

from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path
from typing import Iterable

from ai_pm_agent.portfolio_risk_cockpit.exposure import (
    calculate_concentration_top5,
    calculate_exposure_by_currency,
    calculate_exposure_by_region,
    calculate_exposure_by_theme,
    calculate_exposure_by_ticker,
    calculate_totals,
    collect_warning_codes,
)
from ai_pm_agent.portfolio_risk_cockpit.loader import PortfolioRiskCockpitError, load_positions_from_csv
from ai_pm_agent.portfolio_risk_cockpit.models import SAFETY_BOUNDARY, SCHEMA_VERSION, PortfolioRiskCockpitResult
from ai_pm_agent.portfolio_risk_cockpit.report_writer import write_outputs
from ai_pm_agent.portfolio_risk_cockpit.stress import calculate_stress_scenarios


def run_cockpit(
    *,
    input_path: str | Path,
    out_dir: str | Path | None = None,
    as_of_date: str | None = None,
) -> PortfolioRiskCockpitResult:
    positions = load_positions_from_csv(input_path)
    report_date = as_of_date or date.today().isoformat()

    exposure_by_ticker = calculate_exposure_by_ticker(positions)
    exposure_by_theme = calculate_exposure_by_theme(positions)
    exposure_by_currency = calculate_exposure_by_currency(positions)
    exposure_by_region = calculate_exposure_by_region(positions)
    stress_scenarios = calculate_stress_scenarios(positions)
    warning_codes = collect_warning_codes(positions)
    needs_review_count = sum(1 for position in positions if position.is_needs_review)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": report_date,
        "input_path": str(Path(input_path)),
        "boundary": dict(SAFETY_BOUNDARY),
        "counts": {
            "positions": len(positions),
            "needs_review": needs_review_count,
            "warnings": len(warning_codes),
        },
        "totals": calculate_totals(positions),
        "warning_codes": warning_codes,
        "concentration_top5": calculate_concentration_top5(positions),
        "exposure_by_region": exposure_by_region,
    }
    result = PortfolioRiskCockpitResult(
        as_of_date=report_date,
        input_path=str(Path(input_path)),
        positions=positions,
        exposure_by_ticker=exposure_by_ticker,
        exposure_by_theme=exposure_by_theme,
        exposure_by_currency=exposure_by_currency,
        exposure_by_region=exposure_by_region,
        stress_scenarios=stress_scenarios,
        summary=summary,
        warning_codes=warning_codes,
    )
    files = write_outputs(result, out_dir=out_dir)
    return PortfolioRiskCockpitResult(**{**result.__dict__, "files": files})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an offline Portfolio Risk Cockpit report.")
    parser.add_argument("--input", required=True, help="Local fixture CSV input path.")
    parser.add_argument("--out-dir", help="Output directory. Defaults under ignored reports/ path.")
    parser.add_argument("--as-of-date", help="As-of date to stamp in outputs, YYYY-MM-DD.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Accepted for explicit safety. The runner is offline-only in this phase.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = run_cockpit(input_path=args.input, out_dir=args.out_dir, as_of_date=args.as_of_date)
    except PortfolioRiskCockpitError as exc:
        print(f"Portfolio Risk Cockpit failed closed: {exc}", file=sys.stderr)
        return 2

    print(f"Portfolio Risk Cockpit wrote {len(result.files)} files")
    for label, path in sorted(result.files.items()):
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

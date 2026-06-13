"""Offline Short Put Risk Monitor runner."""

from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path
from typing import Iterable

from ai_pm_agent.short_put_risk_monitor.loader import ShortPutRiskMonitorError, load_short_puts_from_csv
from ai_pm_agent.short_put_risk_monitor.models import SAFETY_BOUNDARY, SCHEMA_VERSION, ShortPutRiskMonitorResult
from ai_pm_agent.short_put_risk_monitor.report_writer import write_outputs
from ai_pm_agent.short_put_risk_monitor.risk_calculator import (
    build_position_rows,
    calculate_totals,
    collect_warning_codes,
)
from ai_pm_agent.short_put_risk_monitor.stress import calculate_stress_rows


def run_monitor(
    *,
    input_path: str | Path,
    out_dir: str | Path | None = None,
    as_of_date: str | None = None,
) -> ShortPutRiskMonitorResult:
    positions = load_short_puts_from_csv(input_path)
    report_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    position_rows = build_position_rows(positions, as_of_date=report_date)
    position_warning_codes = {
        str(row["option_id"]): [code for code in str(row.get("warning_codes", "")).split(";") if code]
        for row in position_rows
    }
    stress_rows = calculate_stress_rows(positions, position_warning_codes=position_warning_codes)
    warning_codes = collect_warning_codes(position_rows + stress_rows)
    needs_review_count = sum(1 for row in position_rows if row["review_status"] == "NEEDS_REVIEW")
    summary = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": report_date.isoformat(),
        "input_path": str(Path(input_path)),
        "boundary": dict(SAFETY_BOUNDARY),
        "counts": {
            "positions": len(positions),
            "stress_rows": len(stress_rows),
            "needs_review": needs_review_count,
            "warnings": len(warning_codes),
        },
        "totals": calculate_totals(position_rows),
        "warning_codes": warning_codes,
    }
    result = ShortPutRiskMonitorResult(
        as_of_date=report_date.isoformat(),
        input_path=str(Path(input_path)),
        positions=positions,
        position_rows=position_rows,
        stress_rows=stress_rows,
        summary=summary,
        warning_codes=warning_codes,
    )
    files = write_outputs(result, out_dir=out_dir)
    return ShortPutRiskMonitorResult(**{**result.__dict__, "files": files})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an offline Short Put Risk Monitor report.")
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
        result = run_monitor(input_path=args.input, out_dir=args.out_dir, as_of_date=args.as_of_date)
    except (ShortPutRiskMonitorError, ValueError) as exc:
        print(f"Short Put Risk Monitor failed closed: {exc}", file=sys.stderr)
        return 2

    print(f"Short Put Risk Monitor wrote {len(result.files)} files")
    for label, path in sorted(result.files.items()):
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

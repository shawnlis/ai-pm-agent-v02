"""Output writers for the offline Short Put Risk Monitor."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from ai_pm_agent.short_put_risk_monitor.models import ShortPutRiskMonitorResult
from ai_pm_agent.short_put_risk_monitor.schema import (
    POSITIONS_FILENAME,
    REPORT_FILENAME,
    SHORT_PUT_POSITION_FIELDS,
    SHORT_PUT_STRESS_FIELDS,
    STRESS_FILENAME,
    SUMMARY_FILENAME,
    WARNINGS_FILENAME,
)


def default_output_dir() -> Path:
    return Path("reports") / "short_put_risk_monitor" / "v051" / date.today().strftime("%Y%m%d")


def write_outputs(result: ShortPutRiskMonitorResult, out_dir: str | Path | None = None) -> dict[str, str]:
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    target.mkdir(parents=True, exist_ok=True)

    report_path = target / REPORT_FILENAME
    summary_path = target / SUMMARY_FILENAME
    positions_path = target / POSITIONS_FILENAME
    stress_path = target / STRESS_FILENAME
    warnings_path = target / WARNINGS_FILENAME

    _write_csv(positions_path, SHORT_PUT_POSITION_FIELDS, result.position_rows)
    _write_csv(stress_path, SHORT_PUT_STRESS_FIELDS, result.stress_rows)
    summary_path.write_text(json.dumps(result.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_path.write_text(_warnings_markdown(result), encoding="utf-8")
    report_path.write_text(_report_markdown(result), encoding="utf-8")

    return {
        "report": str(report_path),
        "summary": str(summary_path),
        "positions": str(positions_path),
        "stress_scenarios": str(stress_path),
        "warnings": str(warnings_path),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _report_markdown(result: ShortPutRiskMonitorResult) -> str:
    totals = result.summary["totals"]
    lines = [
        "# Short Put Risk Monitor v0.5.1",
        "",
        "This is a short put risk report, not an options trading recommendation.",
        "",
        "## Run Metadata",
        "",
        f"- As-of date: `{result.as_of_date}`",
        f"- Input: `{result.input_path}`",
        f"- Position rows: `{len(result.positions)}`",
        f"- Gross notional: `{_money(float(totals['gross_notional']))}`",
        f"- Assignment notional: `{_money(float(totals['assignment_notional']))}`",
        f"- Premium collected: `{_money(float(totals['premium_collected']))}`",
        "",
        "## Boundaries",
        "",
        "- Fixture CSV input only.",
        "- No broker connection, order placement, live market data, yfinance, web search, or external AI model workflow.",
        "- No roll, close, open, sizing, or PM recommendation wiring.",
        "",
        "## Position Risk Table",
        "",
        _positions_table(result.position_rows),
        "",
        "## Stress Scenarios",
        "",
        _stress_table(result.stress_rows),
        "",
        "## Review Warnings",
        "",
    ]
    if result.warning_codes:
        lines.extend(f"- `{code}`" for code in result.warning_codes)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _warnings_markdown(result: ShortPutRiskMonitorResult) -> str:
    lines = [
        "# Short Put Risk Monitor v0.5.1 Warnings",
        "",
        "This is a short put risk report, not an options trading recommendation.",
        "",
    ]
    if not result.warning_codes:
        lines.append("- No warning codes.")
    else:
        for code in result.warning_codes:
            lines.append(f"- `{code}`")
    lines.extend(
        [
            "",
            "Boundary:",
            "",
            "- No order, roll, close, open, sizing, or trade instruction is produced.",
            "- Rows marked `NEEDS_REVIEW` require manual review before use in any downstream memo.",
            "",
        ]
    )
    return "\n".join(lines)


def _positions_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Option | Underlying | Expiry | Strike | Price | Breakeven | Assignment Notional | Review | Warnings |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {option_id} | {underlying} | {expiry} | {strike} | {price} | {breakeven} | {assignment} | {review} | {warnings} |".format(
                option_id=row["option_id"],
                underlying=row["underlying_ticker"],
                expiry=row["expiry_date"] or "UNKNOWN",
                strike=_money(float(row["strike"])),
                price="" if row["current_underlying_price"] == "" else _money(float(row["current_underlying_price"])),
                breakeven=_money(float(row["breakeven_price"])),
                assignment=_money(float(row["assignment_notional"])),
                review=row["review_status"],
                warnings=row["warning_codes"],
            )
        )
    return "\n".join(lines)


def _stress_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Option | Scenario | Stress Price | Downside After Premium | Estimated P/L After Premium | Review | Warnings |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {option_id} | {scenario} | {stress_price} | {downside} | {pnl} | {review} | {warnings} |".format(
                option_id=row["option_id"],
                scenario=row["scenario"],
                stress_price="" if row["stress_price"] == "" else _money(float(row["stress_price"])),
                downside=_money(float(row["max_simple_downside_at_stress"])),
                pnl=_money(float(row["estimated_pnl_at_stress"])),
                review=row["review_status"],
                warnings=row["warning_codes"],
            )
        )
    return "\n".join(lines)


def _money(value: float) -> str:
    return f"{value:,.2f}"

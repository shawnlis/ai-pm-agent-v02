"""Output writers for the offline Portfolio Risk Cockpit."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from ai_pm_agent.portfolio_risk_cockpit.models import PortfolioRiskCockpitResult
from ai_pm_agent.portfolio_risk_cockpit.schema import (
    CURRENCY_EXPOSURE_FILENAME,
    EXPOSURE_BY_BUCKET_FIELDS,
    EXPOSURE_BY_TICKER_FIELDS,
    REPORT_FILENAME,
    STRESS_SCENARIO_FIELDS,
    STRESS_SCENARIOS_FILENAME,
    SUMMARY_FILENAME,
    THEME_EXPOSURE_FILENAME,
    TICKER_EXPOSURE_FILENAME,
    WARNINGS_FILENAME,
)


def default_output_dir() -> Path:
    return Path("reports") / "portfolio_risk_cockpit" / "v050" / date.today().strftime("%Y%m%d")


def write_outputs(result: PortfolioRiskCockpitResult, out_dir: str | Path | None = None) -> dict[str, str]:
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    target.mkdir(parents=True, exist_ok=True)

    report_path = target / REPORT_FILENAME
    summary_path = target / SUMMARY_FILENAME
    ticker_path = target / TICKER_EXPOSURE_FILENAME
    theme_path = target / THEME_EXPOSURE_FILENAME
    currency_path = target / CURRENCY_EXPOSURE_FILENAME
    stress_path = target / STRESS_SCENARIOS_FILENAME
    warnings_path = target / WARNINGS_FILENAME

    _write_csv(ticker_path, EXPOSURE_BY_TICKER_FIELDS, result.exposure_by_ticker)
    _write_csv(theme_path, EXPOSURE_BY_BUCKET_FIELDS, result.exposure_by_theme)
    _write_csv(currency_path, EXPOSURE_BY_BUCKET_FIELDS, result.exposure_by_currency)
    _write_csv(stress_path, STRESS_SCENARIO_FIELDS, result.stress_scenarios)
    summary_path.write_text(json.dumps(result.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_path.write_text(_warnings_markdown(result), encoding="utf-8")
    report_path.write_text(_report_markdown(result), encoding="utf-8")

    return {
        "report": str(report_path),
        "summary": str(summary_path),
        "exposure_by_ticker": str(ticker_path),
        "exposure_by_theme": str(theme_path),
        "exposure_by_currency": str(currency_path),
        "stress_scenarios": str(stress_path),
        "risk_warnings": str(warnings_path),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _report_markdown(result: PortfolioRiskCockpitResult) -> str:
    totals = result.summary["totals"]
    lines = [
        "# Portfolio Risk Cockpit v0.5.0 Phase 1",
        "",
        "This is a risk report, not an investment recommendation.",
        "",
        "## Run Metadata",
        "",
        f"- As-of date: `{result.as_of_date}`",
        f"- Input: `{result.input_path}`",
        f"- Position rows: `{len(result.positions)}`",
        f"- Gross market value: `{_money(float(totals['gross_market_value']))}`",
        f"- Gross exposure: `{_money(float(totals['gross_exposure']))}`",
        f"- Leverage-adjusted exposure: `{_money(float(totals['leverage_adjusted_exposure']))}`",
        "",
        "## Boundaries",
        "",
        "- Local/offline fixture CSV input only.",
        "- No broker connection, order placement, live market data, web search, yfinance, or external AI model workflow.",
        "- No PM prompt wiring and no portfolio-aware PM recommendation path.",
        "- Short option and unknown instrument rows are marked `NEEDS_REVIEW`.",
        "",
        "## Top 5 Concentration",
        "",
        _table(result.summary["concentration_top5"], "ticker"),
        "",
        "## Exposure By Ticker",
        "",
        _table(result.exposure_by_ticker, "ticker"),
        "",
        "## Exposure By Theme",
        "",
        _table(result.exposure_by_theme, "bucket"),
        "",
        "## Exposure By Currency",
        "",
        _table(result.exposure_by_currency, "bucket"),
        "",
        "## Stress Scenarios",
        "",
        _stress_table(result.stress_scenarios),
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


def _warnings_markdown(result: PortfolioRiskCockpitResult) -> str:
    lines = [
        "# Portfolio Risk Cockpit v0.5.0 Warnings",
        "",
        "This is a risk report, not an investment recommendation.",
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
            "- No buy, sell, hold, sizing, rebalance, order, or trade instruction is produced.",
            "- Rows marked `NEEDS_REVIEW` require manual review before use in any downstream memo.",
            "",
        ]
    )
    return "\n".join(lines)


def _table(rows: list[dict[str, Any]], first_field: str) -> str:
    if not rows:
        return "| Bucket | Exposure |\n| --- | ---: |\n| n/a | 0.0% |"
    lines = [
        "| Bucket | Gross Market Value | Leverage-Adjusted Exposure | % L-A Exposure | Review |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {bucket} | {market} | {adjusted} | {pct} | {review} |".format(
                bucket=row[first_field],
                market=_money(float(row["gross_market_value"])),
                adjusted=_money(float(row["leverage_adjusted_exposure"])),
                pct=_pct(float(row["pct_leverage_adjusted_exposure"])),
                review=row["review_status"],
            )
        )
    return "\n".join(lines)


def _stress_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Scenario | Shock | Impacted Exposure | Estimated Impact | Impact / Gross MV | Review | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {shock} | {exposure} | {impact} | {pct} | {review} | {warnings} |".format(
                scenario=row["scenario"],
                shock=_pct(float(row["shock_pct"])),
                exposure=_money(float(row["impacted_exposure"])),
                impact=_money(float(row["estimated_impact_value"])),
                pct=_pct(float(row["estimated_impact_pct_of_gross_market_value"])),
                review=row.get("review_status", ""),
                warnings=row.get("warning_codes", ""),
            )
        )
    return "\n".join(lines)


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"

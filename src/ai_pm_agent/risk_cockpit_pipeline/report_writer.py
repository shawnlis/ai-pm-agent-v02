"""Output writer for Risk Cockpit Pipeline v0.5.2."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from ai_pm_agent.risk_cockpit_pipeline.models import RiskCockpitPipelineResult
from ai_pm_agent.risk_cockpit_pipeline.schema import (
    ARTIFACT_SUMMARY_FIELDS,
    ARTIFACT_SUMMARY_FILENAME,
    ENRICHMENT_SUMMARY_FIELDS,
    ENRICHMENT_SUMMARY_FILENAME,
    INDEX_FILENAME,
    MARKET_DATA_SNAPSHOT_FIELDS,
    MARKET_DATA_SNAPSHOT_FILENAME,
    REPORT_FILENAME,
    WARNING_SUMMARY_FIELDS,
    WARNING_SUMMARY_FILENAME,
    WARNINGS_FILENAME,
)


def default_output_dir() -> Path:
    return Path("reports") / "risk_cockpit_pipeline" / "v052" / date.today().strftime("%Y%m%d")


def write_outputs(result: RiskCockpitPipelineResult, out_dir: str | Path | None = None) -> dict[str, str]:
    target = Path(out_dir) if out_dir is not None else Path(result.output_dir)
    target.mkdir(parents=True, exist_ok=True)

    paths = {
        "report": target / REPORT_FILENAME,
        "index": target / INDEX_FILENAME,
        "artifact_summary": target / ARTIFACT_SUMMARY_FILENAME,
        "warning_summary": target / WARNING_SUMMARY_FILENAME,
        "market_data_snapshot": target / MARKET_DATA_SNAPSHOT_FILENAME,
        "enrichment_summary": target / ENRICHMENT_SUMMARY_FILENAME,
        "warnings": target / WARNINGS_FILENAME,
    }
    files_created = [str(path) for path in paths.values()]
    index = {**result.index, "files_created": files_created}

    _write_csv(paths["artifact_summary"], ARTIFACT_SUMMARY_FIELDS, result.artifact_rows)
    _write_csv(paths["warning_summary"], WARNING_SUMMARY_FIELDS, result.warning_rows)
    _write_csv(paths["market_data_snapshot"], MARKET_DATA_SNAPSHOT_FIELDS, result.market_data_rows)
    _write_csv(paths["enrichment_summary"], ENRICHMENT_SUMMARY_FIELDS, result.enrichment_rows)
    paths["index"].write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["warnings"].write_text(_warnings_markdown(result), encoding="utf-8")
    paths["report"].write_text(_report_markdown(result), encoding="utf-8")
    return {label: str(path) for label, path in paths.items()}


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _report_markdown(result: RiskCockpitPipelineResult) -> str:
    lines = [
        "# Risk Cockpit Pipeline v0.5.2",
        "",
        "This is a risk review pipeline, not an investment recommendation.",
        "",
        "## Executive Risk Review Status",
        "",
        f"- Run ID: `{result.run_id}`",
        f"- As-of date: `{result.as_of_date}`",
        f"- Review required: `{result.review_required}`",
        f"- Warning codes: `{', '.join(result.warning_codes) if result.warning_codes else 'None'}`",
        "",
        "## Artifact Coverage Summary",
        "",
        _artifact_table(result.artifact_rows),
        "",
        "## Warning Summary",
        "",
        _warning_table(result.warning_rows),
        "",
        "## Market Data Coverage Summary",
        "",
        _market_table(result.market_data_rows),
        "",
        "## Enrichment Review Summary",
        "",
        _enrichment_table(result.enrichment_rows),
        "",
        "## Manual Review Checklist",
        "",
        "- Review all NEEDS_REVIEW rows from Portfolio Risk Cockpit.",
        "- Review all short put warnings, especially below strike, below breakeven, expired, and large assignment notional.",
        "- Review missing, stale, or mismatched market data.",
        "- Do not treat positive estimated P/L as an opportunity signal.",
        "- Do not use outputs as buy/sell/hold/roll/close/open/sizing advice.",
        "",
        "## Safety Boundaries",
        "",
        "- Local/offline risk review only.",
        "- Fixture market data only; no live market data.",
        "- No broker connection, IBKR content inspection, trading, order placement, web search, yfinance, or external AI workflow.",
        "- No client data, PM prompt wiring, recommendation output, or options advice.",
        "- Market data is review context only and does not overwrite source risk inputs.",
        "",
    ]
    return "\n".join(lines)


def _warnings_markdown(result: RiskCockpitPipelineResult) -> str:
    lines = [
        "# Risk Cockpit Pipeline v0.5.2 Warnings",
        "",
        "This is a risk review pipeline, not an investment recommendation.",
        "",
    ]
    if not result.warning_rows:
        lines.append("- No warning codes.")
    else:
        for row in result.warning_rows:
            lines.append(
                f"- `{row['warning_code']}` from `{row['source']}` count `{row['count']}` review `{row['review_required']}`"
            )
    lines.extend(
        [
            "",
            "Boundary:",
            "",
            "- No trade, order, market-data-live, broker, client-advice, or PM recommendation action is produced.",
            "- Rows marked for review require manual review before downstream use.",
            "",
        ]
    )
    return "\n".join(lines)


def _artifact_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Artifact | Status | Rows | Warnings | Review |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['artifact_type']} | {row['status']} | {row['row_count']} | {row['warning_count']} | {row['review_required']} |"
        )
    return "\n".join(lines)


def _warning_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "| Source | Warning | Count | Review |\n| --- | --- | ---: | --- |\n| n/a | None | 0 | False |"
    lines = [
        "| Source | Warning | Count | Review |",
        "| --- | --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['source']} | {row['warning_code']} | {row['count']} | {row['review_required']} |")
    return "\n".join(lines)


def _market_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Ticker | Price | Date | Source | Status | Warnings |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['ticker']} | {row['price']} | {row['as_of_date']} | {row['source']} | {row['status']} | {row['warning_codes']} |"
        )
    return "\n".join(lines)


def _enrichment_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Ticker | Context | Market Data | Stale | Review | Warnings |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {ticker} | {context} | {available} | {stale} | {review} | {warnings} |".format(
                ticker=row["ticker"],
                context=row["source_context"],
                available=row["market_data_available"],
                stale=row["stale_market_data"],
                review=row["review_required"],
                warnings=row["warning_codes"],
            )
        )
    return "\n".join(lines)

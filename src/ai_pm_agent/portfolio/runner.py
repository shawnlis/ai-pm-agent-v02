"""Offline portfolio exposure report runner.

This module reads local static portfolio inputs and writes deterministic
exposure reports. It does not fetch broker data, prices, FX rates, ETF
constituents, LLM output, or any external data.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from ai_pm_agent.portfolio.exposure import (
    calculate_base_leverage_adjusted_gross_exposure,
    calculate_base_market_value,
    calculate_base_market_value_exposure,
    calculate_concentration_summary,
    calculate_country_of_risk_exposure,
    calculate_currency_exposure,
    calculate_industry_exposure,
    calculate_instrument_type_exposure,
    calculate_issuer_exposure,
    calculate_lookthrough_exposure,
    calculate_lookthrough_sector_exposure,
    calculate_region_exposure,
    calculate_sector_exposure,
    calculate_theme_exposure,
)
from ai_pm_agent.portfolio.models import Holding, LookThroughComponent, PortfolioSnapshot


HOLDINGS_REQUIRED_COLUMNS = {"portfolio_id", "as_of_date", "ticker", "quantity"}
HOLDING_FLOAT_FIELDS = {
    "quantity",
    "market_value_local",
    "fx_rate_to_base",
    "market_value_base",
    "leverage_factor",
}
LOOKTHROUGH_FLOAT_FIELDS = {"component_weight"}
MAPPING_FILL_FIELDS = {
    "issuer_name",
    "issuer_canonical_id",
    "underlying_issuer_name",
    "underlying_ticker",
    "listing_country",
    "country_of_risk",
    "region",
    "sector",
    "industry",
    "themes",
}


class PortfolioRunnerError(ValueError):
    """Raised when local portfolio input files are malformed."""


@dataclass(frozen=True)
class InputTable:
    path: Path
    rows: list[dict[str, str]]
    columns: set[str]


@dataclass(frozen=True)
class PortfolioRunResult:
    snapshot: PortfolioSnapshot
    warnings: list[str]
    input_files: dict[str, str | None]
    exposures: dict[str, dict[str, float]]
    concentration: dict[str, object]


def run_from_paths(
    *,
    holdings_path: str | Path,
    out_path: str | Path,
    json_out_path: str | Path | None = None,
    issuer_mapping_path: str | Path | None = None,
    taxonomy_mapping_path: str | Path | None = None,
    manual_lookthrough_path: str | Path | None = None,
    fx_snapshot_path: str | Path | None = None,
) -> PortfolioRunResult:
    holdings = _read_required_table(Path(holdings_path), "holdings")
    _require_columns(holdings, HOLDINGS_REQUIRED_COLUMNS)

    warnings: list[str] = []
    issuer_mapping = _read_optional_table(issuer_mapping_path, "issuer mapping", warnings)
    taxonomy_mapping = _read_optional_table(taxonomy_mapping_path, "taxonomy mapping", warnings)
    manual_lookthrough = _read_optional_table(manual_lookthrough_path, "manual look-through", warnings)
    fx_snapshot = _read_optional_table(fx_snapshot_path, "FX snapshot", warnings)

    snapshot = build_snapshot_from_tables(
        holdings=holdings,
        issuer_mapping=issuer_mapping,
        taxonomy_mapping=taxonomy_mapping,
        manual_lookthrough=manual_lookthrough,
        fx_snapshot=fx_snapshot,
        warnings=warnings,
    )
    result = build_run_result(
        snapshot=snapshot,
        warnings=warnings,
        input_files={
            "holdings": str(Path(holdings_path)),
            "issuer_mapping": _path_or_none(issuer_mapping_path),
            "taxonomy_mapping": _path_or_none(taxonomy_mapping_path),
            "manual_lookthrough": _path_or_none(manual_lookthrough_path),
            "fx_snapshot": _path_or_none(fx_snapshot_path),
        },
    )

    write_markdown_report(result, Path(out_path))
    if json_out_path is not None:
        write_json_summary(result, Path(json_out_path))
    return result


def build_snapshot_from_tables(
    *,
    holdings: InputTable,
    issuer_mapping: InputTable | None = None,
    taxonomy_mapping: InputTable | None = None,
    manual_lookthrough: InputTable | None = None,
    fx_snapshot: InputTable | None = None,
    warnings: list[str] | None = None,
) -> PortfolioSnapshot:
    warnings = warnings if warnings is not None else []
    issuer_by_ticker = _rows_by_ticker(issuer_mapping)
    taxonomy_by_ticker = _rows_by_ticker(taxonomy_mapping)
    fx_by_pair = _fx_by_pair(fx_snapshot)
    lookthrough_by_ticker = _lookthrough_by_parent(manual_lookthrough, warnings)

    portfolio_id: str | None = None
    as_of_date: str | None = None
    base_currency: str | None = None
    holding_models: list[Holding] = []

    for row_number, raw_row in enumerate(holdings.rows, start=2):
        row = dict(raw_row)
        ticker = _normalize_ticker(row.get("ticker", ""))
        if not ticker:
            raise PortfolioRunnerError(f"holdings row {row_number}: ticker must not be blank")

        if portfolio_id is None:
            portfolio_id = row.get("portfolio_id")
        elif row.get("portfolio_id") and row.get("portfolio_id") != portfolio_id:
            warnings.append(
                f"holdings row {row_number}: portfolio_id {row.get('portfolio_id')} differs from {portfolio_id}"
            )

        if as_of_date is None:
            as_of_date = row.get("as_of_date")
        elif row.get("as_of_date") and row.get("as_of_date") != as_of_date:
            warnings.append(f"holdings row {row_number}: as_of_date {row.get('as_of_date')} differs from {as_of_date}")

        _apply_mapping(row, issuer_by_ticker.get(ticker))
        _apply_mapping(row, taxonomy_by_ticker.get(ticker))

        row_base_currency = _clean_value(row.get("base_currency")) or "USD"
        row_trading_currency = _clean_value(row.get("trading_currency")) or row_base_currency
        row["base_currency"] = row_base_currency
        row["trading_currency"] = row_trading_currency
        row.setdefault("currency", row_trading_currency)

        if base_currency is None:
            base_currency = row_base_currency
        elif row_base_currency != base_currency:
            warnings.append(
                f"{ticker}: base_currency {row_base_currency} differs from portfolio base currency {base_currency}"
            )

        if _is_blank(row.get("fx_rate_to_base")):
            fx_rate = fx_by_pair.get((row_trading_currency.upper(), row_base_currency.upper()))
            if fx_rate is not None:
                row["fx_rate_to_base"] = str(fx_rate)

        if row_trading_currency.upper() != row_base_currency.upper() and _is_blank(row.get("fx_rate_to_base")):
            warnings.append(f"{ticker}: missing FX rate for {row_trading_currency}->{row_base_currency}")

        if _is_blank(row.get("market_value_base")):
            if not _is_blank(row.get("market_value_local")) and not _is_blank(row.get("fx_rate_to_base")):
                local_value = _parse_float(row["market_value_local"], "market_value_local", f"holdings row {row_number}")
                fx_rate = _parse_float(row["fx_rate_to_base"], "fx_rate_to_base", f"holdings row {row_number}")
                row["market_value_base"] = str(local_value * fx_rate)
            elif _is_blank(row.get("market_value_local")):
                warnings.append(f"{ticker}: missing market_value_base and market_value_local")
            else:
                warnings.append(f"{ticker}: missing market_value_base; using local value fallback")

        if _is_blank(row.get("issuer_canonical_id")):
            warnings.append(f"{ticker}: missing issuer mapping")
        if _is_blank(row.get("sector")) or _is_blank(row.get("industry")) or _is_blank(row.get("country_of_risk")):
            warnings.append(f"{ticker}: missing taxonomy metadata")

        holding_models.append(_holding_from_row(row, ticker, lookthrough_by_ticker.get(ticker, []), row_number))

    if not as_of_date:
        raise PortfolioRunnerError("holdings input must include as_of_date")

    return PortfolioSnapshot(
        as_of_date=as_of_date,
        base_currency=base_currency or "USD",
        cash=0.0,
        cash_currency=base_currency or "USD",
        holdings=holding_models,
        benchmark=None,
        notes=f"Offline portfolio input runner; portfolio_id={portfolio_id or 'unknown'}",
    )


def build_run_result(
    *,
    snapshot: PortfolioSnapshot,
    warnings: list[str],
    input_files: dict[str, str | None],
) -> PortfolioRunResult:
    exposures = {
        "sector": calculate_sector_exposure(snapshot),
        "industry": calculate_industry_exposure(snapshot),
        "region": calculate_region_exposure(snapshot),
        "country_of_risk": calculate_country_of_risk_exposure(snapshot),
        "issuer": calculate_issuer_exposure(snapshot),
        "instrument_type": calculate_instrument_type_exposure(snapshot),
        "theme": calculate_theme_exposure(snapshot),
        "currency": calculate_currency_exposure(snapshot),
        "base_market_value": calculate_base_market_value_exposure(snapshot),
        "lookthrough_sector": calculate_lookthrough_sector_exposure(snapshot),
        "lookthrough_issuer": calculate_lookthrough_exposure(snapshot, "issuer"),
        "lookthrough_theme": calculate_lookthrough_exposure(snapshot, "theme"),
    }
    concentration = calculate_concentration_summary(snapshot)
    return PortfolioRunResult(
        snapshot=snapshot,
        warnings=sorted(set(warnings)),
        input_files=input_files,
        exposures=exposures,
        concentration=concentration,
    )


def write_markdown_report(result: PortfolioRunResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = result.snapshot
    portfolio_id = _portfolio_id_from_notes(snapshot.notes)

    sections = [
        "# Portfolio Exposure Report",
        "",
        "This is a local/offline informational exposure report generated from user-supplied static inputs.",
        "",
        "- No broker connection was used.",
        "- No live market data, live FX, yfinance, web search, LLM, OpenRouter, or DeepSeek workflow was used.",
        "- No ETF, fund, crypto ETF, or index constituents were fetched.",
        "- Portfolio data is not wired into PM recommendations, ratings, actions, or research execution.",
        "- This report is not investment advice, trading advice, suitability advice, VaR, or a risk model.",
        "",
        "## Run Metadata",
        "",
        f"- Portfolio ID: `{portfolio_id}`",
        f"- As-of date: `{snapshot.as_of_date}`",
        f"- Base currency: `{snapshot.base_currency}`",
        f"- Holding count: `{len(snapshot.holdings)}`",
        f"- Total base equity value: {_money(snapshot.total_base_equity_value)}",
        f"- Leverage-adjusted gross exposure: {_pct(calculate_base_leverage_adjusted_gross_exposure(snapshot))}",
        "",
        _input_files_section(result.input_files),
        "",
        _warnings_section(result.warnings),
        "",
        _holdings_section(snapshot),
        "",
        _exposure_section("Sector Exposure", result.exposures["sector"]),
        "",
        _exposure_section("Industry Exposure", result.exposures["industry"]),
        "",
        _exposure_section("Region Exposure", result.exposures["region"]),
        "",
        _exposure_section("Country-Of-Risk Exposure", result.exposures["country_of_risk"]),
        "",
        _exposure_section("Issuer Exposure", result.exposures["issuer"]),
        "",
        _exposure_section("Instrument-Type Exposure", result.exposures["instrument_type"]),
        "",
        _exposure_section("Theme Exposure", result.exposures["theme"]),
        "",
        _exposure_section("Currency Exposure", result.exposures["currency"]),
        "",
        _exposure_section("Base-Market-Value Exposure", result.exposures["base_market_value"]),
        "",
        _concentration_section(result.concentration),
        "",
        _exposure_section("Manual Look-Through Sector Exposure", result.exposures["lookthrough_sector"]),
        "",
        _exposure_section("Manual Look-Through Issuer Exposure", result.exposures["lookthrough_issuer"]),
        "",
        _exposure_section("Manual Look-Through Theme Exposure", result.exposures["lookthrough_theme"]),
        "",
        "## Limitations",
        "",
        "- All market values, FX rates, issuer mappings, taxonomy labels, and look-through weights are user-supplied.",
        "- Missing base values fall back according to the portfolio model and may not be FX-normalized.",
        "- Look-through residuals are not inferred unless supplied as manual residual components.",
        "- Cash is treated as already being in the snapshot base currency.",
        "- Taxonomy values are local strings and are not normalized to GICS, BICS, ISO, MSCI, broker, or provider standards.",
        "- Leverage-adjusted gross exposure is a notional-style reporting helper, not VaR, stress loss, margin, or risk-adjusted exposure.",
        "",
    ]
    out_path.write_text("\n".join(sections), encoding="utf-8")


def write_json_summary(result: PortfolioRunResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = result.snapshot
    payload = {
        "portfolio_id": _portfolio_id_from_notes(snapshot.notes),
        "as_of_date": str(snapshot.as_of_date),
        "base_currency": snapshot.base_currency,
        "counts": {
            "holdings": len(snapshot.holdings),
            "warnings": len(result.warnings),
        },
        "warnings": result.warnings,
        "input_files": result.input_files,
        "exposures": result.exposures,
        "leverage_adjusted_gross_exposure": calculate_base_leverage_adjusted_gross_exposure(snapshot),
        "concentration": result.concentration,
        "lookthrough_summary": {
            "holdings_with_manual_lookthrough": [
                holding.ticker for holding in snapshot.holdings if holding.lookthrough_components
            ],
            "sector": result.exposures["lookthrough_sector"],
            "issuer": result.exposures["lookthrough_issuer"],
            "theme": result.exposures["lookthrough_theme"],
        },
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_required_table(path: Path, label: str) -> InputTable:
    if not path.exists():
        raise PortfolioRunnerError(f"{label} file not found: {path}")
    return _read_table(path)


def _read_optional_table(path_value: str | Path | None, label: str, warnings: list[str]) -> InputTable | None:
    if path_value is None:
        return None
    path = Path(path_value)
    if not path.exists():
        warnings.append(f"optional {label} file not found: {path}")
        return None
    return _read_table(path)


def _read_table(path: Path) -> InputTable:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = {_normalize_column(column) for column in (reader.fieldnames or [])}
            rows = [_clean_row(row) for row in reader]
        return InputTable(path=path, rows=rows, columns=columns)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            raw_rows = data["rows"]
        elif isinstance(data, list):
            raw_rows = data
        else:
            raise PortfolioRunnerError(f"JSON input must be a list of rows or an object with rows: {path}")
        rows = [_clean_row(row) for row in raw_rows]
        columns = set().union(*(row.keys() for row in rows)) if rows else set()
        return InputTable(path=path, rows=rows, columns=columns)
    raise PortfolioRunnerError(f"unsupported input format for {path}; use CSV or JSON")


def _require_columns(table: InputTable, required_columns: set[str]) -> None:
    missing = sorted(required_columns - table.columns)
    if missing:
        raise PortfolioRunnerError(f"{table.path} missing required columns: {', '.join(missing)}")


def _clean_row(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        raise PortfolioRunnerError("input rows must be objects")
    return {_normalize_column(str(key)): _clean_value(value) for key, value in row.items()}


def _normalize_column(value: str) -> str:
    return value.strip().lower()


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return _clean_value(value) == ""


def _normalize_ticker(value: str) -> str:
    return value.strip().upper()


def _path_or_none(path_value: str | Path | None) -> str | None:
    return None if path_value is None else str(Path(path_value))


def _rows_by_ticker(table: InputTable | None) -> dict[str, dict[str, str]]:
    if table is None:
        return {}
    rows: dict[str, dict[str, str]] = {}
    for row in table.rows:
        ticker = _normalize_ticker(row.get("ticker", ""))
        if ticker:
            rows[ticker] = row
    return rows


def _fx_by_pair(table: InputTable | None) -> dict[tuple[str, str], float]:
    if table is None:
        return {}
    rows: dict[tuple[str, str], float] = {}
    for row_number, row in enumerate(table.rows, start=2):
        currency = row.get("currency", "").upper()
        base_currency = row.get("base_currency", "").upper()
        if not currency or not base_currency:
            continue
        rows[(currency, base_currency)] = _parse_float(row.get("fx_rate_to_base"), "fx_rate_to_base", f"FX row {row_number}")
    return rows


def _lookthrough_by_parent(table: InputTable | None, warnings: list[str]) -> dict[str, list[LookThroughComponent]]:
    if table is None:
        return {}
    grouped: dict[str, list[LookThroughComponent]] = {}
    for row_number, row in enumerate(table.rows, start=2):
        parent_ticker = _normalize_ticker(row.get("parent_ticker", ""))
        if not parent_ticker:
            warnings.append(f"manual look-through row {row_number}: missing parent_ticker")
            continue
        component = LookThroughComponent(
            holding_ticker=parent_ticker,
            component_issuer_name=_none_if_blank(row.get("component_issuer_name")),
            component_issuer_canonical_id=_none_if_blank(row.get("component_issuer_canonical_id")),
            component_ticker=_none_if_blank(row.get("component_ticker")),
            component_weight=_parse_float(
                row.get("component_weight"),
                "component_weight",
                f"manual look-through row {row_number}",
            ),
            sector=_none_if_blank(row.get("sector")),
            industry=_none_if_blank(row.get("industry")),
            country_of_risk=_none_if_blank(row.get("country_of_risk")),
            region=_none_if_blank(row.get("region")),
            theme=_split_themes(row.get("themes")),
            source_note=_none_if_blank(row.get("source_note")),
        )
        grouped.setdefault(parent_ticker, []).append(component)

    for parent_ticker, components in sorted(grouped.items()):
        total = sum(component.component_weight for component in components)
        if abs(total - 1.0) > 0.000001:
            warnings.append(f"{parent_ticker}: manual look-through weights sum to {total:.4f}, not 1.0000")
    return grouped


def _apply_mapping(row: dict[str, str], mapping_row: dict[str, str] | None) -> None:
    if not mapping_row:
        return
    for field in MAPPING_FILL_FIELDS:
        if _is_blank(row.get(field)) and not _is_blank(mapping_row.get(field)):
            row[field] = mapping_row[field]


def _holding_from_row(
    row: dict[str, str],
    ticker: str,
    lookthrough_components: list[LookThroughComponent],
    row_number: int,
) -> Holding:
    parsed: dict[str, Any] = {
        "ticker": ticker,
        "name": _none_if_blank(row.get("name")),
        "quantity": _parse_float(row.get("quantity"), "quantity", f"holdings row {row_number}"),
        "market_value_local": _parse_optional_float(row.get("market_value_local"), "market_value_local", row_number),
        "fx_rate_to_base": _parse_optional_float(row.get("fx_rate_to_base"), "fx_rate_to_base", row_number),
        "market_value_base": _parse_optional_float(row.get("market_value_base"), "market_value_base", row_number),
        "instrument_type": _none_if_blank(row.get("instrument_type")),
        "asset_class": _none_if_blank(row.get("instrument_type")) or "equity",
        "issuer_name": _none_if_blank(row.get("issuer_name")),
        "issuer_canonical_id": _none_if_blank(row.get("issuer_canonical_id")),
        "underlying_issuer_name": _none_if_blank(row.get("underlying_issuer_name")),
        "underlying_ticker": _none_if_blank(row.get("underlying_ticker")),
        "listing_country": _none_if_blank(row.get("listing_country")),
        "country_of_risk": _none_if_blank(row.get("country_of_risk")),
        "region": _none_if_blank(row.get("region")),
        "sector": _none_if_blank(row.get("sector")),
        "industry": _none_if_blank(row.get("industry")),
        "theme": _split_themes(row.get("themes")),
        "trading_currency": _none_if_blank(row.get("trading_currency")) or _none_if_blank(row.get("base_currency")),
        "currency": _none_if_blank(row.get("trading_currency")) or _none_if_blank(row.get("base_currency")) or "USD",
        "base_currency": _none_if_blank(row.get("base_currency")),
        "leverage_factor": _parse_optional_float(row.get("leverage_factor"), "leverage_factor", row_number),
        "notes": _none_if_blank(row.get("notes")),
        "lookthrough_components": lookthrough_components,
    }
    return Holding(**parsed)


def _parse_optional_float(value: Any, field: str, row_number: int) -> float | None:
    if _is_blank(value):
        return None
    return _parse_float(value, field, f"holdings row {row_number}")


def _parse_float(value: Any, field: str, context: str) -> float:
    if _is_blank(value):
        raise PortfolioRunnerError(f"{context}: missing numeric value for {field}")
    try:
        return float(str(value).replace(",", ""))
    except ValueError as exc:
        raise PortfolioRunnerError(f"{context}: invalid numeric value for {field}: {value}") from exc


def _none_if_blank(value: Any) -> str | None:
    return None if _is_blank(value) else _clean_value(value)


def _split_themes(value: Any) -> list[str]:
    text = _clean_value(value)
    if not text:
        return []
    separators = [";", "|"]
    parts = [text]
    for separator in separators:
        if separator in text:
            parts = text.split(separator)
            break
    if len(parts) == 1 and "," in text:
        parts = text.split(",")
    return [part.strip() for part in parts if part.strip()]


def _portfolio_id_from_notes(notes: str | None) -> str:
    if not notes:
        return "unknown"
    marker = "portfolio_id="
    if marker not in notes:
        return "unknown"
    return notes.split(marker, 1)[1].strip() or "unknown"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.0f}"


def _sorted_exposures(exposure: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(exposure.items(), key=lambda item: (-abs(item[1]), item[0]))


def _input_files_section(input_files: dict[str, str | None]) -> str:
    lines = ["## Input Files", "", "| Input | Path |", "| --- | --- |"]
    for label, path in sorted(input_files.items()):
        lines.append(f"| {label} | `{path or 'not provided'}` |")
    return "\n".join(lines)


def _warnings_section(warnings: list[str]) -> str:
    lines = ["## Validation Warnings", ""]
    if not warnings:
        lines.append("- None")
    else:
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines)


def _holdings_section(snapshot: PortfolioSnapshot) -> str:
    lines = [
        "## Line-Item Holdings",
        "",
        "| Ticker | Name | Instrument | Issuer ID | Trading currency | Base market value | Leverage | Sector | Country of risk | Themes |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for holding in snapshot.holdings:
        lines.append(
            "| "
            + " | ".join(
                [
                    holding.ticker,
                    holding.name or "",
                    holding.instrument_type or holding.asset_class,
                    holding.issuer_canonical_id or holding.issuer_name or holding.ticker,
                    holding.trading_currency or holding.currency,
                    _money(calculate_base_market_value(holding)),
                    f"{holding.leverage_factor or holding.leverage_multiplier:.1f}x",
                    holding.sector or "",
                    holding.country_of_risk or "",
                    ", ".join(holding.theme),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _exposure_section(title: str, exposure: dict[str, float]) -> str:
    lines = [f"## {title}", "", "| Bucket | Exposure |", "| --- | ---: |"]
    if not exposure:
        lines.append("| n/a | 0.0% |")
    else:
        for bucket, value in _sorted_exposures(exposure):
            lines.append(f"| {bucket} | {_pct(value)} |")
    return "\n".join(lines)


def _concentration_section(concentration: dict[str, object]) -> str:
    lines = [
        "## Concentration Summary",
        "",
        f"- Holding count: `{concentration['holding_count']}`",
        f"- Total base equity value: {_money(float(concentration['total_base_equity_value']))}",
        "",
        "### Top Holdings",
        "",
        "| Ticker | Issuer | Base market value | Weight |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in concentration["top_holdings"]:
        lines.append(
            f"| {row['ticker']} | {row['issuer']} | {_money(float(row['market_value_base']))} | {_pct(float(row['weight']))} |"
        )
    lines.extend(["", "### Top Issuers", "", "| Issuer | Weight |", "| --- | ---: |"])
    for row in concentration["top_issuers"]:
        lines.append(f"| {row['issuer']} | {_pct(float(row['weight']))} |")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an offline portfolio exposure report from local files.")
    parser.add_argument("--holdings", required=True, help="Local holdings CSV or JSON file.")
    parser.add_argument("--issuer-mapping", help="Optional local issuer mapping CSV or JSON file.")
    parser.add_argument("--taxonomy-mapping", help="Optional local taxonomy mapping CSV or JSON file.")
    parser.add_argument("--manual-lookthrough", help="Optional local manual look-through CSV or JSON file.")
    parser.add_argument("--fx-snapshot", help="Optional local FX snapshot CSV or JSON file.")
    parser.add_argument("--out", required=True, help="Markdown report output path.")
    parser.add_argument("--json-out", help="JSON summary output path.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = run_from_paths(
            holdings_path=args.holdings,
            issuer_mapping_path=args.issuer_mapping,
            taxonomy_mapping_path=args.taxonomy_mapping,
            manual_lookthrough_path=args.manual_lookthrough,
            fx_snapshot_path=args.fx_snapshot,
            out_path=args.out,
            json_out_path=args.json_out,
        )
    except PortfolioRunnerError as exc:
        print(f"portfolio runner error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote markdown report: {args.out}")
    if args.json_out:
        print(f"wrote JSON summary: {args.json_out}")
    if result.warnings:
        print(f"warnings: {len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

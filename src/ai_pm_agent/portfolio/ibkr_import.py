"""Offline IBKR statement import adapter.

This module converts local IBKR-exported CSV or Flex-style CSV rows into the
Phase 3C portfolio input format. It never connects to IBKR, broker APIs, live
market data, FX services, LLMs, or external providers.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


PHASE3C_HOLDINGS_FIELDS = [
    "portfolio_id",
    "as_of_date",
    "ticker",
    "name",
    "quantity",
    "market_value_local",
    "trading_currency",
    "base_currency",
    "fx_rate_to_base",
    "market_value_base",
    "instrument_type",
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
    "leverage_factor",
    "notes",
]

REVIEW_FIELDS = [
    "source_file",
    "source_row_number",
    "source_section",
    "parse_status",
    "review_required",
    "warnings",
    *PHASE3C_HOLDINGS_FIELDS,
    "ibkr_asset_category",
    "ibkr_security_type",
    "ibkr_conid",
    "ibkr_isin",
    "ibkr_exchange",
    "ibkr_account",
]

SUMMARY_FILE = "ibkr_import_summary.json"
WARNINGS_FILE = "ibkr_import_warnings.md"
REVIEW_FILE = "parsed_holdings_review.csv"
READY_FILE = "portfolio_runner_ready_holdings.csv"

TICKER_ALIASES = ["symbol", "ticker", "local symbol", "ibkr symbol"]
NAME_ALIASES = ["description", "name", "security description"]
QUANTITY_ALIASES = ["quantity", "position", "qty", "shares", "ending quantity"]
TRADING_CURRENCY_ALIASES = ["currency", "currencyprimary", "trading currency"]
BASE_CURRENCY_ALIASES = ["base currency", "basecurrency", "reporting currency"]
MARKET_VALUE_LOCAL_ALIASES = ["market value", "marketvalue", "current value", "ending value", "value"]
MARKET_VALUE_BASE_ALIASES = [
    "market value in base",
    "market value base",
    "marketvaluebase",
    "base market value",
    "market value (base)",
]
FX_ALIASES = ["fx rate to base", "fxratetobase", "exchange rate", "rate"]
ASSET_CATEGORY_ALIASES = ["asset category", "assetcategory", "asset class"]
SECURITY_TYPE_ALIASES = ["security type", "securitytype", "sec type", "sectype"]
ISSUER_ALIASES = ["issuer", "issuer name"]
UNDERLYING_TICKER_ALIASES = ["underlying symbol", "underlyingsymbol", "underlying"]
LISTING_COUNTRY_ALIASES = ["listing country", "country", "country of listing"]
EXCHANGE_ALIASES = ["listing exchange", "exchange", "primary exchange"]
CONID_ALIASES = ["conid", "contract id", "contractid"]
ISIN_ALIASES = ["isin", "security id"]
ACCOUNT_ALIASES = ["account", "account id", "accountid"]
DATE_ALIASES = ["as of date", "date", "report date", "statement date"]

CASH_ASSET_MARKERS = {"cash", "cash and cash equivalents", "forex", "fx", "money market"}
SUPPORTED_POSITION_SECTIONS = {"open positions", "positions", "open position", "position"}


class IbkrImportError(ValueError):
    """Raised when local IBKR statement input cannot be parsed."""


@dataclass(frozen=True)
class SourceRow:
    path: Path
    row_number: int
    section: str
    values: dict[str, str]


@dataclass(frozen=True)
class ImportResult:
    portfolio_id: str
    as_of_date: str
    base_currency: str
    input_files: list[str]
    output_files: dict[str, str]
    review_rows: list[dict[str, str]]
    ready_rows: list[dict[str, str]]
    warnings: list[str]

    @property
    def summary(self) -> dict[str, Any]:
        excluded = sum(1 for row in self.review_rows if row["parse_status"] == "excluded")
        return {
            "portfolio_id": self.portfolio_id,
            "as_of_date": self.as_of_date,
            "base_currency": self.base_currency,
            "input_files": self.input_files,
            "output_files": self.output_files,
            "counts": {
                "review_rows": len(self.review_rows),
                "ready_holdings": len(self.ready_rows),
                "excluded_rows": excluded,
                "warnings": len(self.warnings),
            },
            "warnings": self.warnings,
            "review_required": True,
            "offline_only": True,
            "notes": [
                "No IBKR connection was used.",
                "No broker API was used.",
                "Imported holdings are not verified until a human reviews parsed_holdings_review.csv and ibkr_import_warnings.md.",
            ],
        }


def import_ibkr_statement_files(
    *,
    input_paths: Iterable[str | Path],
    out_dir: str | Path,
    portfolio_id: str,
    as_of_date: str | None = None,
    base_currency: str = "USD",
) -> ImportResult:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    normalized_base_currency = base_currency.strip().upper()
    if not normalized_base_currency:
        raise IbkrImportError("base_currency must not be blank")

    source_rows: list[SourceRow] = []
    input_file_strings: list[str] = []
    warnings: list[str] = []
    for input_path in input_paths:
        path = Path(input_path)
        input_file_strings.append(str(path))
        source_rows.extend(_read_source_rows(path))

    if not source_rows:
        raise IbkrImportError("no parseable statement rows found")

    resolved_as_of_date = _resolve_as_of_date(source_rows, as_of_date, warnings)

    review_rows: list[dict[str, str]] = []
    ready_rows: list[dict[str, str]] = []
    for source_row in source_rows:
        review_row, ready_row = _map_source_row(
            source_row=source_row,
            portfolio_id=portfolio_id,
            as_of_date=resolved_as_of_date,
            base_currency=normalized_base_currency,
            warnings=warnings,
        )
        review_rows.append(review_row)
        if ready_row is not None:
            ready_rows.append(ready_row)

    output_files = {
        "parsed_holdings_review": str(out_path / REVIEW_FILE),
        "portfolio_runner_ready_holdings": str(out_path / READY_FILE),
        "warnings": str(out_path / WARNINGS_FILE),
        "summary": str(out_path / SUMMARY_FILE),
    }

    result = ImportResult(
        portfolio_id=portfolio_id,
        as_of_date=resolved_as_of_date,
        base_currency=normalized_base_currency,
        input_files=input_file_strings,
        output_files=output_files,
        review_rows=review_rows,
        ready_rows=ready_rows,
        warnings=sorted(set(warnings)),
    )
    _write_csv(Path(output_files["parsed_holdings_review"]), REVIEW_FIELDS, result.review_rows)
    _write_csv(Path(output_files["portfolio_runner_ready_holdings"]), PHASE3C_HOLDINGS_FIELDS, result.ready_rows)
    _write_warnings_markdown(result)
    Path(output_files["summary"]).write_text(json.dumps(result.summary, indent=2, sort_keys=True), encoding="utf-8")
    return result


def _read_source_rows(path: Path) -> list[SourceRow]:
    if not path.exists():
        raise IbkrImportError(f"input file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise IbkrImportError(f"unsupported IBKR input format for {path}; CSV only")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = [row for row in csv.reader(handle)]

    sectioned_rows = _read_sectioned_flex_rows(path, raw_rows)
    if sectioned_rows:
        return sectioned_rows
    return _read_header_csv_rows(path, raw_rows)


def _read_header_csv_rows(path: Path, raw_rows: list[list[str]]) -> list[SourceRow]:
    if not raw_rows:
        return []
    header = [_normalize_column(column) for column in raw_rows[0]]
    rows: list[SourceRow] = []
    for row_number, raw_row in enumerate(raw_rows[1:], start=2):
        if not any(str(value).strip() for value in raw_row):
            continue
        values = {header[index]: _clean_value(raw_row[index]) if index < len(raw_row) else "" for index in range(len(header))}
        rows.append(SourceRow(path=path, row_number=row_number, section="", values=values))
    return rows


def _read_sectioned_flex_rows(path: Path, raw_rows: list[list[str]]) -> list[SourceRow]:
    headers_by_section: dict[str, list[str]] = {}
    parsed_rows: list[SourceRow] = []

    for row_number, raw_row in enumerate(raw_rows, start=1):
        if len(raw_row) < 3:
            continue
        section = _clean_value(raw_row[0])
        row_type = _clean_value(raw_row[1]).lower()
        section_key = section.lower()
        if row_type == "header":
            headers_by_section[section_key] = [_normalize_column(column) for column in raw_row[2:]]
            continue
        if row_type != "data" or section_key not in headers_by_section:
            continue
        if not _is_supported_section(section):
            continue
        header = headers_by_section[section_key]
        values = {header[index]: _clean_value(raw_row[index + 2]) if index + 2 < len(raw_row) else "" for index in range(len(header))}
        parsed_rows.append(SourceRow(path=path, row_number=row_number, section=section, values=values))
    return parsed_rows


def _is_supported_section(section: str) -> bool:
    text = section.strip().lower()
    return not text or any(marker in text for marker in SUPPORTED_POSITION_SECTIONS)


def _resolve_as_of_date(source_rows: list[SourceRow], explicit_as_of_date: str | None, warnings: list[str]) -> str:
    if explicit_as_of_date:
        return explicit_as_of_date
    dates = sorted({value for row in source_rows if (value := _first_value(row.values, DATE_ALIASES, []))})
    if len(dates) == 1:
        return dates[0]
    if len(dates) > 1:
        warnings.append(f"multiple statement dates found; using {dates[-1]}")
        return dates[-1]
    warnings.append("as_of_date not found in input; using today's local date")
    return date.today().isoformat()


def _map_source_row(
    *,
    source_row: SourceRow,
    portfolio_id: str,
    as_of_date: str,
    base_currency: str,
    warnings: list[str],
) -> tuple[dict[str, str], dict[str, str] | None]:
    row_warnings: list[str] = []
    values = source_row.values

    asset_category = _first_value(values, ASSET_CATEGORY_ALIASES, row_warnings)
    security_type = _first_value(values, SECURITY_TYPE_ALIASES, row_warnings)
    ticker = _normalize_ticker(_first_value(values, TICKER_ALIASES, row_warnings))
    name = _first_value(values, NAME_ALIASES, row_warnings)
    quantity_text = _first_value(values, QUANTITY_ALIASES, row_warnings)
    trading_currency = (_first_value(values, TRADING_CURRENCY_ALIASES, row_warnings) or base_currency).upper()
    row_base_currency = (_first_value(values, BASE_CURRENCY_ALIASES, row_warnings) or base_currency).upper()
    market_value_local = _first_value(values, MARKET_VALUE_LOCAL_ALIASES, row_warnings)
    market_value_base = _first_value(values, MARKET_VALUE_BASE_ALIASES, row_warnings)
    fx_rate_to_base = _first_value(values, FX_ALIASES, row_warnings)
    issuer_name = _first_value(values, ISSUER_ALIASES, row_warnings)
    underlying_ticker = _normalize_ticker(_first_value(values, UNDERLYING_TICKER_ALIASES, row_warnings))
    listing_country = _first_value(values, LISTING_COUNTRY_ALIASES, row_warnings)
    exchange = _first_value(values, EXCHANGE_ALIASES, row_warnings)
    conid = _first_value(values, CONID_ALIASES, row_warnings)
    isin = _first_value(values, ISIN_ALIASES, row_warnings)
    account = _first_value(values, ACCOUNT_ALIASES, row_warnings)

    instrument_type = _instrument_type(asset_category, security_type, row_warnings)
    notes = _notes(source_row, asset_category, security_type, conid, isin, exchange, account)

    parse_status = "ready_for_review"
    ready_row: dict[str, str] | None = None

    if _is_cash_like(asset_category, security_type, ticker):
        parse_status = "excluded"
        row_warnings.append("cash-like row not converted; multi-currency cash requires manual review")
    elif not ticker:
        parse_status = "excluded"
        row_warnings.append("missing ticker; row excluded")
    elif not quantity_text:
        parse_status = "excluded"
        row_warnings.append("missing quantity; row excluded")
    else:
        quantity = _parse_number_text(quantity_text, "quantity", row_warnings)
        if quantity is None:
            parse_status = "excluded"
            row_warnings.append("invalid quantity; row excluded")
        else:
            local_value = _parse_number_text(market_value_local, "market_value_local", row_warnings)
            base_value = _parse_number_text(market_value_base, "market_value_base", row_warnings)
            fx_rate = _parse_number_text(fx_rate_to_base, "fx_rate_to_base", row_warnings)
            if market_value_local and local_value is None:
                market_value_local = ""
            if market_value_base and base_value is None:
                market_value_base = ""
            if fx_rate_to_base and fx_rate is None:
                fx_rate_to_base = ""
            if not market_value_local and not market_value_base:
                row_warnings.append("missing market value; output row requires human valuation review")
            if trading_currency != row_base_currency and not market_value_base and not fx_rate_to_base:
                row_warnings.append("non-base-currency row lacks base value and FX rate")

            ready_row = {
                "portfolio_id": portfolio_id,
                "as_of_date": as_of_date,
                "ticker": ticker,
                "name": name,
                "quantity": _number_to_text(quantity),
                "market_value_local": _number_to_text(local_value) if local_value is not None else "",
                "trading_currency": trading_currency,
                "base_currency": row_base_currency,
                "fx_rate_to_base": _number_to_text(fx_rate) if fx_rate is not None else "",
                "market_value_base": _number_to_text(base_value) if base_value is not None else "",
                "instrument_type": instrument_type,
                "issuer_name": issuer_name,
                "issuer_canonical_id": "",
                "underlying_issuer_name": "",
                "underlying_ticker": underlying_ticker,
                "listing_country": listing_country,
                "country_of_risk": "",
                "region": "",
                "sector": "",
                "industry": "",
                "themes": "",
                "leverage_factor": "",
                "notes": notes,
            }
            row_warnings.append("human review required before using this row in exposure reports")

    source_prefix = f"{source_row.path.name}: row {source_row.row_number}"
    for warning in row_warnings:
        warnings.append(f"{source_prefix}: {warning}")

    mapped = ready_row or {
        "portfolio_id": portfolio_id,
        "as_of_date": as_of_date,
        "ticker": ticker,
        "name": name,
        "quantity": quantity_text,
        "market_value_local": market_value_local,
        "trading_currency": trading_currency,
        "base_currency": row_base_currency,
        "fx_rate_to_base": fx_rate_to_base,
        "market_value_base": market_value_base,
        "instrument_type": instrument_type,
        "issuer_name": issuer_name,
        "issuer_canonical_id": "",
        "underlying_issuer_name": "",
        "underlying_ticker": underlying_ticker,
        "listing_country": listing_country,
        "country_of_risk": "",
        "region": "",
        "sector": "",
        "industry": "",
        "themes": "",
        "leverage_factor": "",
        "notes": notes,
    }

    review_row = {
        "source_file": str(source_row.path),
        "source_row_number": str(source_row.row_number),
        "source_section": source_row.section,
        "parse_status": parse_status,
        "review_required": "true",
        "warnings": "; ".join(row_warnings),
        **mapped,
        "ibkr_asset_category": asset_category,
        "ibkr_security_type": security_type,
        "ibkr_conid": conid,
        "ibkr_isin": isin,
        "ibkr_exchange": exchange,
        "ibkr_account": account,
    }
    return review_row, ready_row


def _first_value(row: dict[str, str], aliases: list[str], warnings: list[str]) -> str:
    found: list[tuple[str, str]] = []
    for alias in aliases:
        value = row.get(_normalize_column(alias), "")
        if value:
            found.append((alias, value))
    distinct_values = {value for _, value in found}
    if len(distinct_values) > 1:
        names = ", ".join(alias for alias, _ in found)
        warnings.append(f"ambiguous values for {names}; using {found[0][1]}")
    return found[0][1] if found else ""


def _instrument_type(asset_category: str, security_type: str, warnings: list[str]) -> str:
    text = f"{asset_category} {security_type}".strip().lower()
    if any(token in text for token in ["stock", "stk", "equity", "common"]):
        return "stock"
    if "leveraged" in text and "etf" in text:
        return "leveraged_etf"
    if "etf" in text:
        return "etf"
    if any(token in text for token in ["bond", "fixed income"]):
        return "note"
    if any(token in text for token in ["fund", "mutual"]):
        return "fund"
    if any(token in text for token in CASH_ASSET_MARKERS):
        return "cash"
    if not text:
        warnings.append("missing asset category/security type; using other instrument_type")
    else:
        warnings.append(f"unmapped asset category/security type '{text}'; using other instrument_type")
    return "other"


def _is_cash_like(asset_category: str, security_type: str, ticker: str) -> bool:
    text = f"{asset_category} {security_type} {ticker}".strip().lower()
    return any(marker in text for marker in CASH_ASSET_MARKERS)


def _parse_number_text(value: str, field: str, warnings: list[str]) -> float | None:
    text = _clean_value(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("$", "")
    try:
        parsed = float(text)
    except ValueError:
        warnings.append(f"invalid numeric value for {field}: {value}")
        return None
    return -parsed if negative else parsed


def _number_to_text(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _notes(
    source_row: SourceRow,
    asset_category: str,
    security_type: str,
    conid: str,
    isin: str,
    exchange: str,
    account: str,
) -> str:
    details = [
        "IBKR_IMPORT_REVIEW_REQUIRED",
        f"source_file={source_row.path.name}",
        f"source_row={source_row.row_number}",
    ]
    if source_row.section:
        details.append(f"section={source_row.section}")
    if asset_category:
        details.append(f"asset_category={asset_category}")
    if security_type:
        details.append(f"security_type={security_type}")
    if conid:
        details.append(f"conid={conid}")
    if isin:
        details.append(f"isin={isin}")
    if exchange:
        details.append(f"exchange={exchange}")
    if account:
        details.append(f"account={account}")
    return "; ".join(details)


def _normalize_ticker(value: str) -> str:
    return _clean_value(value).upper()


def _normalize_column(value: str) -> str:
    text = re.sub(r"\s+", " ", _clean_value(value)).lower()
    return text


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_warnings_markdown(result: ImportResult) -> None:
    path = Path(result.output_files["warnings"])
    lines = [
        "# IBKR Import Warnings",
        "",
        "This is a local/offline review artifact generated from user-supplied IBKR statement exports.",
        "",
        "- No IBKR connection was used.",
        "- No broker API was used.",
        "- No credentials, API keys, or tokens are required.",
        "- Imported holdings are not verified until reviewed by a human.",
        "- Do not use `portfolio_runner_ready_holdings.csv` for exposure reporting until this review is complete.",
        "",
        "## Run Metadata",
        "",
        f"- Portfolio ID: `{result.portfolio_id}`",
        f"- As-of date: `{result.as_of_date}`",
        f"- Base currency: `{result.base_currency}`",
        f"- Ready holdings: `{len(result.ready_rows)}`",
        f"- Review rows: `{len(result.review_rows)}`",
        f"- Warning count: `{len(result.warnings)}`",
        "",
        "## Warnings",
        "",
    ]
    if result.warnings:
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Required Human Review",
            "",
            "- Confirm tickers, quantities, currencies, and market values against the original statement.",
            "- Add or review issuer canonical IDs, country-of-risk, region, sector, industry, and themes.",
            "- Review cash and FX rows manually; multi-currency cash is not converted by this adapter.",
            "- Treat all rows as unverified until `parsed_holdings_review.csv` has been reviewed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert local IBKR statement CSV files into Phase 3C portfolio inputs.")
    parser.add_argument("--input", action="append", required=True, help="Local IBKR CSV/Flex-style CSV file. Repeat for multiple files.")
    parser.add_argument("--out-dir", required=True, help="Output directory for review CSV, runner CSV, warnings, and JSON summary.")
    parser.add_argument("--portfolio-id", required=True, help="Portfolio ID to write into the Phase 3C holdings CSV.")
    parser.add_argument("--as-of-date", help="As-of date to write into outputs. Defaults to statement date if found.")
    parser.add_argument("--base-currency", default="USD", help="Portfolio base currency. Defaults to USD.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = import_ibkr_statement_files(
            input_paths=args.input,
            out_dir=args.out_dir,
            portfolio_id=args.portfolio_id,
            as_of_date=args.as_of_date,
            base_currency=args.base_currency,
        )
    except IbkrImportError as exc:
        print(f"ibkr import error: {exc}", file=sys.stderr)
        return 2

    print(f"wrote parsed review CSV: {result.output_files['parsed_holdings_review']}")
    print(f"wrote runner-ready holdings CSV: {result.output_files['portfolio_runner_ready_holdings']}")
    print(f"wrote warnings: {result.output_files['warnings']}")
    print(f"wrote JSON summary: {result.output_files['summary']}")
    if result.warnings:
        print(f"warnings: {len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fail-closed CSV loader for the offline Portfolio Risk Cockpit."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ai_pm_agent.portfolio_risk_cockpit.models import (
    NEEDS_REVIEW,
    REVIEW_OK,
    SHORT_OPTION_NEEDS_REVIEW,
    UNKNOWN_INSTRUMENT_TYPE,
    PortfolioRiskPosition,
)
from ai_pm_agent.portfolio_risk_cockpit.schema import PORTFOLIO_INPUT_FIELDS


KNOWN_INSTRUMENT_TYPES = {
    "adr",
    "bond",
    "cash",
    "crypto_etf",
    "equity",
    "etf",
    "fund",
    "gds",
    "leveraged_etf",
    "long_option",
    "note",
    "option",
    "other",
    "short_option",
    "stock",
}


class PortfolioRiskCockpitError(ValueError):
    """Raised when portfolio risk cockpit input fails validation."""


def load_positions_from_csv(path: str | Path) -> list[PortfolioRiskPosition]:
    input_path = Path(path)
    if not input_path.exists():
        raise PortfolioRiskCockpitError(f"portfolio risk input file not found: {input_path}")
    if input_path.suffix.lower() != ".csv":
        raise PortfolioRiskCockpitError("Portfolio Risk Cockpit Phase 1 accepts CSV fixture input only")

    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = {_normalize_column(column) for column in (reader.fieldnames or [])}
        missing_columns = sorted(set(PORTFOLIO_INPUT_FIELDS) - columns)
        if missing_columns:
            raise PortfolioRiskCockpitError(
                f"{input_path} missing required columns: {', '.join(missing_columns)}"
            )
        return [_position_from_row(_clean_row(row), row_number) for row_number, row in enumerate(reader, start=2)]


def _position_from_row(row: dict[str, str], row_number: int) -> PortfolioRiskPosition:
    ticker = _normalize_ticker(row.get("ticker", ""))
    if not ticker:
        raise PortfolioRiskCockpitError(f"row {row_number}: ticker must not be blank")

    currency = _clean_value(row.get("currency")).upper()
    if not currency:
        raise PortfolioRiskCockpitError(f"{ticker}: currency must not be blank")

    instrument_type = _clean_value(row.get("instrument_type")).lower() or "unknown"
    quantity = _parse_float(row.get("quantity"), "quantity", row_number, ticker)
    market_value = _parse_float(row.get("market_value"), "market_value", row_number, ticker)
    notional_value = _parse_float(row.get("notional_value"), "notional_value", row_number, ticker)

    multiplier_text = _clean_value(row.get("exposure_multiplier"))
    if instrument_type == "leveraged_etf" and not multiplier_text:
        raise PortfolioRiskCockpitError(f"{ticker}: leveraged ETF must explicitly show exposure_multiplier")
    exposure_multiplier = _parse_float(multiplier_text or "1", "exposure_multiplier", row_number, ticker)
    if exposure_multiplier <= 0:
        raise PortfolioRiskCockpitError(f"{ticker}: exposure_multiplier must be greater than zero")

    warning_codes: list[str] = []
    review_status = REVIEW_OK
    if instrument_type not in KNOWN_INSTRUMENT_TYPES:
        warning_codes.append(UNKNOWN_INSTRUMENT_TYPE)
        review_status = NEEDS_REVIEW

    if _is_short_option(instrument_type, quantity, market_value, notional_value):
        warning_codes.append(SHORT_OPTION_NEEDS_REVIEW)
        review_status = NEEDS_REVIEW

    return PortfolioRiskPosition(
        ticker=ticker,
        instrument_type=instrument_type,
        quantity=quantity,
        currency=currency,
        market_value=market_value,
        notional_value=notional_value,
        exposure_multiplier=exposure_multiplier,
        underlying_ticker=_optional_ticker(row.get("underlying_ticker")),
        themes=tuple(_split_themes(row.get("theme"))),
        region=_clean_value(row.get("region")) or "UNKNOWN",
        notes=_clean_value(row.get("notes")) or None,
        review_status=review_status,
        warning_codes=tuple(dict.fromkeys(warning_codes)),
    )


def _is_short_option(instrument_type: str, quantity: float, market_value: float, notional_value: float) -> bool:
    if instrument_type == "short_option":
        return True
    if instrument_type == "option" and (quantity < 0 or market_value < 0 or notional_value < 0):
        return True
    return False


def _parse_float(value: Any, field: str, row_number: int, ticker: str) -> float:
    text = _clean_value(value)
    if not text:
        raise PortfolioRiskCockpitError(f"{ticker}: missing numeric value for {field} on row {row_number}")
    try:
        return float(text.replace(",", ""))
    except ValueError as exc:
        raise PortfolioRiskCockpitError(f"{ticker}: invalid numeric value for {field} on row {row_number}") from exc


def _clean_row(row: dict[str, Any]) -> dict[str, str]:
    return {_normalize_column(str(key)): _clean_value(value) for key, value in row.items()}


def _normalize_column(value: str) -> str:
    return value.strip().lower()


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_ticker(value: str) -> str:
    return value.strip().upper()


def _optional_ticker(value: Any) -> str | None:
    ticker = _normalize_ticker(_clean_value(value))
    return ticker or None


def _split_themes(value: Any) -> list[str]:
    text = _clean_value(value)
    if not text:
        return ["UNKNOWN"]
    parts = [text]
    for separator in (";", "|", ","):
        if separator in text:
            parts = text.split(separator)
            break
    return [part.strip() for part in parts if part.strip()] or ["UNKNOWN"]

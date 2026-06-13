"""Fail-closed fixture CSV loader for the Short Put Risk Monitor."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from ai_pm_agent.short_put_risk_monitor.models import (
    DISALLOWED_REAL_SHORT_PUT_INPUT,
    MISSING_EXPIRY,
    MISSING_UNDERLYING_PRICE,
    NEEDS_REVIEW,
    REVIEW_NEEDS_REVIEW,
    REVIEW_OK,
    ShortPutPosition,
)
from ai_pm_agent.short_put_risk_monitor.schema import SHORT_PUT_INPUT_FIELDS


class ShortPutRiskMonitorError(ValueError):
    """Raised when Short Put Risk Monitor fixture input fails validation."""


def load_short_puts_from_csv(path: str | Path) -> list[ShortPutPosition]:
    input_path = Path(path)
    _reject_real_data_path(input_path)
    if not input_path.exists():
        raise ShortPutRiskMonitorError(f"short put risk input file not found: {input_path}")
    if input_path.suffix.lower() != ".csv":
        raise ShortPutRiskMonitorError("Short Put Risk Monitor v0.5.1 accepts fixture CSV input only")

    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = {_normalize_column(column) for column in (reader.fieldnames or [])}
        missing_columns = sorted(set(SHORT_PUT_INPUT_FIELDS) - columns)
        if missing_columns:
            raise ShortPutRiskMonitorError(
                f"{input_path} missing required columns: {', '.join(missing_columns)}"
            )
        return [_position_from_row(_clean_row(row), row_number) for row_number, row in enumerate(reader, start=2)]


def _reject_real_data_path(path: Path) -> None:
    text = str(path).lower()
    basename = path.name.lower()
    parts = [part.lower() for part in path.parts]
    disallowed = (
        basename == "portfolio.csv"
        or any("ibkr positions" in part for part in parts)
        or any(marker in text for marker in ("ibkr", "broker", "client"))
    )
    if disallowed:
        raise ShortPutRiskMonitorError(
            f"{DISALLOWED_REAL_SHORT_PUT_INPUT}: Short Put Risk Monitor v0.5.1 accepts fixture CSV input only "
            "and refuses real portfolio/broker/client-looking paths before reading file contents."
        )


def _position_from_row(row: dict[str, str], row_number: int) -> ShortPutPosition:
    option_id = _clean_value(row.get("option_id"))
    if not option_id:
        raise ShortPutRiskMonitorError(f"row {row_number}: option_id must not be blank")

    underlying_ticker = _normalize_ticker(row.get("underlying_ticker", ""))
    if not underlying_ticker:
        raise ShortPutRiskMonitorError(f"{option_id}: underlying_ticker must not be blank")

    currency = _clean_value(row.get("currency")).upper()
    if not currency:
        raise ShortPutRiskMonitorError(f"{option_id}: currency must not be blank")

    strike = _parse_positive_float(row.get("strike"), "strike", option_id, row_number)
    contracts = _parse_positive_float(row.get("contracts"), "contracts", option_id, row_number)
    contract_multiplier = _parse_positive_float(
        row.get("contract_multiplier"),
        "contract_multiplier",
        option_id,
        row_number,
    )
    premium_collected = _parse_non_negative_float(
        row.get("premium_collected"),
        "premium_collected",
        option_id,
        row_number,
    )

    warning_codes: list[str] = []
    expiry = _parse_optional_date(row.get("expiry_date"), option_id, row_number, warning_codes)
    current_price = _parse_optional_price(row.get("current_underlying_price"), option_id, row_number, warning_codes)

    review_status = REVIEW_NEEDS_REVIEW if warning_codes else REVIEW_OK
    if warning_codes and NEEDS_REVIEW not in warning_codes:
        warning_codes.append(NEEDS_REVIEW)

    return ShortPutPosition(
        option_id=option_id,
        underlying_ticker=underlying_ticker,
        expiry_date=expiry,
        strike=strike,
        contracts=contracts,
        contract_multiplier=contract_multiplier,
        premium_collected=premium_collected,
        current_underlying_price=current_price,
        currency=currency,
        underlying_theme=_clean_value(row.get("underlying_theme")) or "UNKNOWN",
        notes=_clean_value(row.get("notes")) or None,
        review_status=review_status,
        warning_codes=tuple(dict.fromkeys(warning_codes)),
    )


def _parse_optional_date(value: Any, option_id: str, row_number: int, warning_codes: list[str]) -> date | None:
    text = _clean_value(value)
    if not text:
        warning_codes.append(MISSING_EXPIRY)
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ShortPutRiskMonitorError(f"{option_id}: invalid expiry_date on row {row_number}; use YYYY-MM-DD") from exc


def _parse_optional_price(value: Any, option_id: str, row_number: int, warning_codes: list[str]) -> float | None:
    text = _clean_value(value)
    if not text:
        warning_codes.append(MISSING_UNDERLYING_PRICE)
        return None
    return _parse_positive_float(text, "current_underlying_price", option_id, row_number)


def _parse_positive_float(value: Any, field: str, option_id: str, row_number: int) -> float:
    parsed = _parse_float(value, field, option_id, row_number)
    if parsed <= 0:
        raise ShortPutRiskMonitorError(f"{option_id}: {field} must be greater than zero on row {row_number}")
    return parsed


def _parse_non_negative_float(value: Any, field: str, option_id: str, row_number: int) -> float:
    parsed = _parse_float(value, field, option_id, row_number)
    if parsed < 0:
        raise ShortPutRiskMonitorError(f"{option_id}: {field} must be non-negative on row {row_number}")
    return parsed


def _parse_float(value: Any, field: str, option_id: str, row_number: int) -> float:
    text = _clean_value(value)
    if not text:
        raise ShortPutRiskMonitorError(f"{option_id}: missing numeric value for {field} on row {row_number}")
    try:
        return float(text.replace(",", ""))
    except ValueError as exc:
        raise ShortPutRiskMonitorError(
            f"{option_id}: invalid numeric value for {field} on row {row_number}"
        ) from exc


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

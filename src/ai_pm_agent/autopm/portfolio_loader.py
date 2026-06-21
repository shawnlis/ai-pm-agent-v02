"""Autopm-only local portfolio loader.

The loader accepts explicit fixture/local autopm CSV or JSON inputs. It rejects
real-data-looking portfolio, account, broker, and statement paths before
reading file contents.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


DISALLOWED_PATH_TERMS = (
    "portfolio.csv",
    "ibkr",
    "ibkr positions",
    "broker",
    "client",
    "account",
    "statement",
)


class AutopmPortfolioLoaderError(ValueError):
    """Raised when autopm portfolio input fails closed."""


def load_autopm_portfolio(path: str | Path) -> PortfolioSnapshot:
    """Load an explicit local autopm portfolio fixture from CSV or JSON."""

    input_path = assert_safe_autopm_portfolio_path(path)
    if input_path.suffix.lower() == ".json":
        return _load_json(input_path)
    if input_path.suffix.lower() == ".csv":
        return _load_csv(input_path)
    raise AutopmPortfolioLoaderError("autopm portfolio loader supports only .csv and .json")


def assert_safe_autopm_portfolio_path(path: str | Path) -> Path:
    input_path = Path(path)
    lowered_parts = [part.lower() for part in input_path.parts]
    lowered_name = input_path.name.lower()
    lowered_text = str(input_path).lower()

    if lowered_name == "portfolio.csv":
        raise AutopmPortfolioLoaderError("refusing portfolio.csv; use an explicit autopm fixture/local file")
    for term in DISALLOWED_PATH_TERMS[1:]:
        if term in lowered_text or term in lowered_parts:
            raise AutopmPortfolioLoaderError(f"refusing real-data-looking path term: {term}")
    if not input_path.exists() or not input_path.is_file():
        raise AutopmPortfolioLoaderError(f"autopm portfolio file not found: {input_path}")
    return input_path


def _load_json(path: Path) -> PortfolioSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AutopmPortfolioLoaderError("autopm portfolio JSON must be an object")
    holdings = payload.get("holdings")
    if not isinstance(holdings, list):
        raise AutopmPortfolioLoaderError("autopm portfolio JSON requires holdings list")
    return PortfolioSnapshot(
        as_of_date=_required_text(payload, "as_of_date"),
        base_currency=_text(payload.get("base_currency")) or "USD",
        cash=_float(payload.get("cash")),
        cash_currency=_text(payload.get("cash_currency")) or "USD",
        notes="autopm local fixture portfolio",
        holdings=[_holding_from_mapping(row) for row in holdings if isinstance(row, dict)],
    )


def _load_csv(path: Path) -> PortfolioSnapshot:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise AutopmPortfolioLoaderError("autopm portfolio CSV contains no rows")
    required = {"as_of_date", "ticker", "quantity", "market_value"}
    missing = required - set().union(*(row.keys() for row in rows))
    if missing:
        raise AutopmPortfolioLoaderError(f"missing required autopm portfolio columns: {', '.join(sorted(missing))}")
    first = rows[0]
    return PortfolioSnapshot(
        as_of_date=_required_text(first, "as_of_date"),
        base_currency=_text(first.get("base_currency")) or "USD",
        cash=_float(first.get("cash")),
        cash_currency=_text(first.get("cash_currency")) or "USD",
        notes="autopm local fixture portfolio",
        holdings=[_holding_from_mapping(row) for row in rows],
    )


def _holding_from_mapping(row: dict[str, Any]) -> Holding:
    return Holding(
        ticker=_required_text(row, "ticker"),
        name=_text(row.get("name")) or None,
        market=_text(row.get("market")) or None,
        quantity=_float(row.get("quantity"), default=1.0),
        market_value=_float(row.get("market_value")),
        market_value_base=_optional_float(row.get("market_value_base")),
        currency=_text(row.get("currency")) or "USD",
        base_currency=_text(row.get("base_currency")) or None,
        theme=_string_list(row.get("theme")),
        region=_text(row.get("region")) or None,
        sector=_text(row.get("sector")) or None,
        issuer_name=_text(row.get("issuer_name")) or None,
        issuer_canonical_id=_text(row.get("issuer_canonical_id")) or None,
        leverage_multiplier=_float(row.get("leverage_multiplier"), default=1.0),
        leverage_factor=_optional_float(row.get("leverage_factor")),
        asset_class=_text(row.get("asset_class")) or "equity",
        instrument_type=_text(row.get("instrument_type")) or None,
    )


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text(row.get(key))
    if not value:
        raise AutopmPortfolioLoaderError(f"required autopm portfolio value missing: {key}")
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, *, default: float = 0.0) -> float:
    if _text(value) == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AutopmPortfolioLoaderError("invalid numeric autopm portfolio value") from exc


def _optional_float(value: Any) -> float | None:
    if _text(value) == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AutopmPortfolioLoaderError("invalid optional numeric autopm portfolio value") from exc


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return [part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip()]

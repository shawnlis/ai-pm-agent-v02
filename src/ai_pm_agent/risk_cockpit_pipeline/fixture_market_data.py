"""Fixture-only market data provider for Risk Cockpit Pipeline."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ai_pm_agent.risk_cockpit_pipeline.models import (
    MARKET_DATA_FIXTURE_ONLY,
    MARKET_DATA_NOT_FIXTURE,
    NO_LIVE_MARKET_DATA,
    MarketDataPoint,
    MarketDataProviderSnapshot,
    RiskCockpitPipelineError,
    assert_safe_input_path,
)
from ai_pm_agent.risk_cockpit_pipeline.schema import MARKET_DATA_FIXTURE_FIELDS


class FixtureMarketDataProvider:
    provider_name = "fixture_market_data"
    provider_level = "Level 0"
    network_access = False
    live_market_data = False
    fixture_only = True

    def load(self, path: str | Path) -> MarketDataProviderSnapshot:
        input_path = assert_safe_input_path(path)
        if not input_path.exists():
            raise RiskCockpitPipelineError(f"market data fixture file not found: {input_path}")
        if input_path.suffix.lower() != ".csv":
            raise RiskCockpitPipelineError("Risk Cockpit Pipeline v0.5.2 accepts CSV market data fixtures only")

        with input_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = {_normalize_column(column) for column in (reader.fieldnames or [])}
            missing_columns = sorted(set(MARKET_DATA_FIXTURE_FIELDS) - columns)
            if missing_columns:
                raise RiskCockpitPipelineError(
                    f"{input_path} missing required columns: {', '.join(missing_columns)}"
                )
            points = [_point_from_row(_clean_row(row), row_number) for row_number, row in enumerate(reader, start=2)]

        return MarketDataProviderSnapshot(
            provider_name=self.provider_name,
            provider_level=self.provider_level,
            network_access=self.network_access,
            live_market_data=self.live_market_data,
            fixture_only=self.fixture_only,
            points=points,
            warning_codes=[MARKET_DATA_FIXTURE_ONLY, NO_LIVE_MARKET_DATA],
        )


def load_fixture_market_data(path: str | Path) -> MarketDataProviderSnapshot:
    return FixtureMarketDataProvider().load(path)


def market_data_snapshot_rows(snapshot: MarketDataProviderSnapshot) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for point in snapshot.points:
        warning_codes = [MARKET_DATA_FIXTURE_ONLY] if point.fixture_only else []
        rows.append(
            {
                "ticker": point.ticker,
                "price": point.price,
                "currency": point.currency,
                "as_of_date": point.as_of_date,
                "source": point.source,
                "source_confidence": point.source_confidence,
                "fixture_only": point.fixture_only,
                "status": "ok",
                "warning_codes": ";".join(warning_codes),
                "notes": point.notes,
            }
        )
    return rows


def _point_from_row(row: dict[str, str], row_number: int) -> MarketDataPoint:
    ticker = _normalize_ticker(row.get("ticker", ""))
    if not ticker:
        raise RiskCockpitPipelineError(f"market data row {row_number}: ticker must not be blank")
    currency = _clean_value(row.get("currency")).upper()
    if not currency:
        raise RiskCockpitPipelineError(f"{ticker}: currency must not be blank")
    as_of_date = _clean_value(row.get("as_of_date"))
    if not as_of_date:
        raise RiskCockpitPipelineError(f"{ticker}: as_of_date must not be blank")
    return MarketDataPoint(
        ticker=ticker,
        price=_parse_positive_float(row.get("price"), "price", ticker, row_number),
        currency=currency,
        as_of_date=as_of_date,
        source=_clean_value(row.get("source")) or "fixture",
        source_confidence=_clean_value(row.get("source_confidence")) or "UNKNOWN",
        fixture_only=_parse_fixture_only(row.get("fixture_only"), ticker, row_number),
        notes=_clean_value(row.get("notes")),
    )


def _parse_positive_float(value: Any, field: str, ticker: str, row_number: int) -> float:
    text = _clean_value(value)
    if not text:
        raise RiskCockpitPipelineError(f"{ticker}: missing numeric value for {field} on row {row_number}")
    try:
        parsed = float(text.replace(",", ""))
    except ValueError as exc:
        raise RiskCockpitPipelineError(f"{ticker}: invalid numeric value for {field} on row {row_number}") from exc
    if parsed <= 0:
        raise RiskCockpitPipelineError(f"{ticker}: {field} must be greater than zero on row {row_number}")
    return parsed


def _parse_fixture_only(value: Any, ticker: str, row_number: int) -> bool:
    text = _clean_value(value).lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    raise RiskCockpitPipelineError(
        f"{MARKET_DATA_NOT_FIXTURE}: {ticker} market data row {row_number} must explicitly declare fixture_only=true"
    )


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

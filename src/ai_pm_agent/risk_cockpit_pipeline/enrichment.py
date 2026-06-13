"""Fixture-only risk enrichment for Risk Cockpit Pipeline."""

from __future__ import annotations

from datetime import date
from typing import Any

from ai_pm_agent.risk_cockpit_pipeline.models import (
    MISSING_MARKET_DATA,
    PRICE_MISMATCH_NEEDS_REVIEW,
    REVIEW_NEEDS_REVIEW,
    RISK_ARTIFACT_NEEDS_REVIEW,
    STALE_MARKET_DATA,
    MarketDataPoint,
    requires_review,
    unique_codes,
)


def build_enrichment_rows(
    *,
    portfolio_ticker_rows: list[dict[str, str]],
    short_put_position_rows: list[dict[str, str]],
    market_points: list[MarketDataPoint],
    as_of_date: str,
    max_market_data_age_days: int,
    price_mismatch_threshold_pct: float,
) -> list[dict[str, object]]:
    market_by_ticker = {point.ticker: point for point in market_points}
    rows: list[dict[str, object]] = []

    for row in portfolio_ticker_rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        rows.append(
            _enrichment_row(
                ticker=ticker,
                source_context="portfolio_exposure",
                market_by_ticker=market_by_ticker,
                as_of_date=as_of_date,
                max_market_data_age_days=max_market_data_age_days,
                price_mismatch_threshold_pct=price_mismatch_threshold_pct,
                source_review_status=str(row.get("review_status", "")),
                source_warning_codes=str(row.get("warning_codes", "")),
                current_price_text="",
            )
        )

    for row in short_put_position_rows:
        ticker = str(row.get("underlying_ticker", "")).strip().upper()
        if not ticker:
            continue
        rows.append(
            _enrichment_row(
                ticker=ticker,
                source_context="short_put_position",
                market_by_ticker=market_by_ticker,
                as_of_date=as_of_date,
                max_market_data_age_days=max_market_data_age_days,
                price_mismatch_threshold_pct=price_mismatch_threshold_pct,
                source_review_status=str(row.get("review_status", "")),
                source_warning_codes=str(row.get("warning_codes", "")),
                current_price_text=str(row.get("current_underlying_price", "")),
            )
        )
    return rows


def _enrichment_row(
    *,
    ticker: str,
    source_context: str,
    market_by_ticker: dict[str, MarketDataPoint],
    as_of_date: str,
    max_market_data_age_days: int,
    price_mismatch_threshold_pct: float,
    source_review_status: str,
    source_warning_codes: str,
    current_price_text: str,
) -> dict[str, object]:
    point = market_by_ticker.get(ticker)
    warnings: list[str] = []
    notes: list[str] = []
    stale = False

    source_codes = [code for code in source_warning_codes.split(";") if code]
    if source_review_status == REVIEW_NEEDS_REVIEW or source_codes:
        warnings.append(RISK_ARTIFACT_NEEDS_REVIEW)
        notes.append("source artifact row requires review")

    if point is None:
        warnings.append(MISSING_MARKET_DATA)
        notes.append("no fixture market data for ticker")
        return _row(
            ticker=ticker,
            source_context=source_context,
            market_data_available=False,
            market_price="",
            market_data_as_of_date="",
            market_data_currency="",
            stale_market_data=False,
            warning_codes=warnings,
            notes=notes,
        )

    stale = _is_stale(point.as_of_date, as_of_date, max_market_data_age_days)
    if stale:
        warnings.append(STALE_MARKET_DATA)
        notes.append("fixture market data is stale versus as-of date")

    if current_price_text:
        current_price = _parse_optional_float(current_price_text)
        if current_price and _price_mismatch(current_price, point.price, price_mismatch_threshold_pct):
            warnings.append(PRICE_MISMATCH_NEEDS_REVIEW)
            notes.append("short put current price differs from fixture market data")

    return _row(
        ticker=ticker,
        source_context=source_context,
        market_data_available=True,
        market_price=point.price,
        market_data_as_of_date=point.as_of_date,
        market_data_currency=point.currency,
        stale_market_data=stale,
        warning_codes=warnings,
        notes=notes,
    )


def _row(
    *,
    ticker: str,
    source_context: str,
    market_data_available: bool,
    market_price: float | str,
    market_data_as_of_date: str,
    market_data_currency: str,
    stale_market_data: bool,
    warning_codes: list[str],
    notes: list[str],
) -> dict[str, object]:
    codes = unique_codes(warning_codes)
    return {
        "ticker": ticker,
        "source_context": source_context,
        "market_data_available": market_data_available,
        "market_price": market_price,
        "market_data_as_of_date": market_data_as_of_date,
        "market_data_currency": market_data_currency,
        "stale_market_data": stale_market_data,
        "warning_codes": ";".join(codes),
        "review_required": requires_review(codes),
        "notes": "; ".join(notes),
    }


def _is_stale(source_date: str, as_of_date: str, max_age_days: int) -> bool:
    try:
        source = date.fromisoformat(source_date)
        target = date.fromisoformat(as_of_date)
    except ValueError:
        return True
    return (target - source).days > max_age_days


def _parse_optional_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _price_mismatch(current_price: float, market_price: float, threshold_pct: float) -> bool:
    if current_price == 0:
        return False
    return abs(market_price - current_price) / abs(current_price) > threshold_pct

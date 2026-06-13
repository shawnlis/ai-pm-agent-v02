"""Deterministic exposure calculations for Portfolio Risk Cockpit v0.5.0."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from ai_pm_agent.portfolio_risk_cockpit.models import NEEDS_REVIEW, REVIEW_OK, PortfolioRiskPosition


def calculate_exposure_by_ticker(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    return _aggregate(
        positions,
        lambda position: [position.ticker],
        bucket_field="ticker",
        include_instrument_count=True,
    )


def calculate_exposure_by_theme(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    return _aggregate(positions, lambda position: list(position.themes), bucket_field="bucket")


def calculate_exposure_by_currency(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    return _aggregate(positions, lambda position: [position.currency], bucket_field="bucket")


def calculate_exposure_by_region(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    return _aggregate(positions, lambda position: [position.region or "UNKNOWN"], bucket_field="bucket")


def calculate_concentration_top5(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    rows = calculate_exposure_by_ticker(positions)
    rows.sort(key=lambda row: (-float(row["gross_market_value"]), str(row["ticker"])))
    return rows[:5]


def calculate_totals(positions: list[PortfolioRiskPosition]) -> dict[str, float]:
    return {
        "gross_market_value": sum(position.gross_market_value for position in positions),
        "gross_exposure": sum(position.gross_exposure_value for position in positions),
        "leverage_adjusted_exposure": sum(position.leverage_adjusted_exposure for position in positions),
    }


def collect_warning_codes(positions: list[PortfolioRiskPosition]) -> list[str]:
    codes = sorted({code for position in positions for code in position.warning_codes})
    return codes


def _aggregate(
    positions: list[PortfolioRiskPosition],
    bucket_getter: Callable[[PortfolioRiskPosition], list[str]],
    *,
    bucket_field: str,
    include_instrument_count: bool = False,
) -> list[dict[str, object]]:
    totals = calculate_totals(positions)
    buckets: dict[str, dict[str, object]] = defaultdict(_empty_bucket)

    for position in positions:
        for bucket in bucket_getter(position):
            key = bucket or "UNKNOWN"
            row = buckets[key]
            row[bucket_field] = key
            row["instrument_count"] = int(row["instrument_count"]) + 1
            row["gross_market_value"] = float(row["gross_market_value"]) + position.gross_market_value
            row["gross_exposure"] = float(row["gross_exposure"]) + position.gross_exposure_value
            row["leverage_adjusted_exposure"] = (
                float(row["leverage_adjusted_exposure"]) + position.leverage_adjusted_exposure
            )
            row["warning_codes_set"].update(position.warning_codes)
            if position.is_needs_review:
                row["review_status"] = NEEDS_REVIEW

    rows: list[dict[str, object]] = []
    for row in buckets.values():
        clean = {
            bucket_field: row[bucket_field],
            "gross_market_value": round(float(row["gross_market_value"]), 6),
            "gross_exposure": round(float(row["gross_exposure"]), 6),
            "leverage_adjusted_exposure": round(float(row["leverage_adjusted_exposure"]), 6),
            "pct_gross_market_value": _ratio(float(row["gross_market_value"]), totals["gross_market_value"]),
            "pct_leverage_adjusted_exposure": _ratio(
                float(row["leverage_adjusted_exposure"]),
                totals["leverage_adjusted_exposure"],
            ),
            "review_status": row["review_status"],
            "warning_codes": ";".join(sorted(row["warning_codes_set"])),
        }
        if include_instrument_count:
            clean["instrument_count"] = int(row["instrument_count"])
        rows.append(clean)

    rows.sort(key=lambda item: (-float(item["leverage_adjusted_exposure"]), str(item[bucket_field])))
    return rows


def _empty_bucket() -> dict[str, object]:
    return {
        "instrument_count": 0,
        "gross_market_value": 0.0,
        "gross_exposure": 0.0,
        "leverage_adjusted_exposure": 0.0,
        "review_status": REVIEW_OK,
        "warning_codes_set": set(),
    }


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 10)

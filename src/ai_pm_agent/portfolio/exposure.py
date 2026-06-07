"""Pure exposure calculation helpers for portfolio snapshots."""

from __future__ import annotations

from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


def calculate_market_value(holding: Holding) -> float | None:
    if holding.market_value is not None:
        return holding.market_value
    if holding.current_price is None:
        return None
    return holding.quantity * holding.current_price


def calculate_weight(holding: Holding, portfolio_total: float) -> float:
    if portfolio_total == 0:
        return 0.0
    market_value = calculate_market_value(holding)
    if market_value is None:
        return 0.0
    return market_value / portfolio_total


def calculate_gross_exposure(snapshot: PortfolioSnapshot) -> float:
    portfolio_total = snapshot.total_equity_value
    if portfolio_total == 0:
        return 0.0
    gross_value = sum(abs(calculate_market_value(holding) or 0.0) for holding in snapshot.holdings)
    return gross_value / portfolio_total


def calculate_leverage_adjusted_exposure(snapshot: PortfolioSnapshot) -> float:
    portfolio_total = snapshot.total_equity_value
    if portfolio_total == 0:
        return 0.0
    adjusted_value = sum(
        abs(calculate_market_value(holding) or 0.0) * holding.leverage_multiplier for holding in snapshot.holdings
    )
    return adjusted_value / portfolio_total


def calculate_theme_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: holding.theme)


def calculate_asset_class_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [holding.asset_class])


def calculate_currency_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [holding.currency])


def calculate_risk_bucket_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.risk_bucket] if holding.risk_bucket else [],
    )


def find_incomplete_valuation_holdings(snapshot: PortfolioSnapshot) -> list[str]:
    return [holding.ticker for holding in snapshot.holdings if calculate_market_value(holding) is None]


def _calculate_bucket_exposure(snapshot: PortfolioSnapshot, bucket_getter) -> dict[str, float]:
    portfolio_total = snapshot.total_equity_value
    exposure: dict[str, float] = {}
    if portfolio_total == 0:
        return exposure

    for holding in snapshot.holdings:
        market_value = calculate_market_value(holding)
        if market_value is None:
            continue
        for bucket in bucket_getter(holding):
            if not bucket:
                continue
            exposure[str(bucket)] = exposure.get(str(bucket), 0.0) + market_value / portfolio_total
    return exposure

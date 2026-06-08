"""Pure exposure calculation helpers for portfolio snapshots."""

from __future__ import annotations

from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


def calculate_market_value(holding: Holding) -> float | None:
    if holding.market_value is not None:
        return holding.market_value
    if holding.current_price is None:
        return None
    return holding.quantity * holding.current_price


def calculate_base_market_value(holding: Holding) -> float | None:
    if holding.market_value_base is not None:
        return holding.market_value_base
    if holding.market_value_local is not None and holding.fx_rate_to_base is not None:
        return holding.market_value_local * holding.fx_rate_to_base
    return calculate_market_value(holding)


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
        abs(calculate_market_value(holding) or 0.0) * _leverage_factor(holding) for holding in snapshot.holdings
    )
    return adjusted_value / portfolio_total


def calculate_leverage_adjusted_gross_exposure(snapshot: PortfolioSnapshot) -> float:
    return calculate_leverage_adjusted_exposure(snapshot)


def calculate_base_leverage_adjusted_gross_exposure(snapshot: PortfolioSnapshot) -> float:
    portfolio_total = _total_base_equity_value(snapshot)
    if portfolio_total == 0:
        return 0.0
    adjusted_value = sum(
        abs(calculate_base_market_value(holding) or 0.0) * _leverage_factor(holding)
        for holding in snapshot.holdings
    )
    return adjusted_value / portfolio_total


def calculate_base_market_value_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    portfolio_total = _total_base_equity_value(snapshot)
    if portfolio_total == 0:
        return {holding.ticker: 0.0 for holding in snapshot.holdings}
    exposure = {
        holding.ticker: (calculate_base_market_value(holding) or 0.0) / portfolio_total
        for holding in snapshot.holdings
    }
    return dict(sorted(exposure.items()))


def calculate_theme_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: holding.theme)


def calculate_asset_class_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [holding.asset_class])


def calculate_currency_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [holding.trading_currency or holding.currency])


def calculate_risk_bucket_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.risk_bucket] if holding.risk_bucket else [],
    )


def calculate_sector_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.sector] if holding.sector else [],
        use_base_value=True,
    )


def calculate_industry_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.industry] if holding.industry else [],
        use_base_value=True,
    )


def calculate_region_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.region] if holding.region else [],
        use_base_value=True,
    )


def calculate_country_of_risk_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(
        snapshot,
        lambda holding: [holding.country_of_risk] if holding.country_of_risk else [],
        use_base_value=True,
    )


def calculate_issuer_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [_issuer_key(holding)], use_base_value=True)


def calculate_instrument_type_exposure(snapshot: PortfolioSnapshot) -> dict[str, float]:
    return _calculate_bucket_exposure(snapshot, lambda holding: [_instrument_type(holding)], use_base_value=True)


def calculate_concentration_summary(snapshot: PortfolioSnapshot, top_n: int = 5) -> dict[str, object]:
    portfolio_total = _total_base_equity_value(snapshot)
    holding_rows: list[dict[str, object]] = []

    for holding in snapshot.holdings:
        market_value = calculate_base_market_value(holding) or 0.0
        weight = 0.0 if portfolio_total == 0 else market_value / portfolio_total
        holding_rows.append(
            {
                "ticker": holding.ticker,
                "issuer": _issuer_key(holding),
                "market_value_base": market_value,
                "weight": weight,
            }
        )

    holding_rows.sort(key=lambda row: (-abs(float(row["weight"])), str(row["ticker"])))
    issuer_rows = [
        {"issuer": issuer, "weight": weight}
        for issuer, weight in calculate_issuer_exposure(snapshot).items()
    ]
    issuer_rows.sort(key=lambda row: (-abs(float(row["weight"])), str(row["issuer"])))

    return {
        "holding_count": len(snapshot.holdings),
        "total_base_equity_value": portfolio_total,
        "largest_holding": holding_rows[0] if holding_rows else None,
        "largest_issuer": issuer_rows[0] if issuer_rows else None,
        "top_holdings": holding_rows[:top_n],
        "top_issuers": issuer_rows[:top_n],
    }


def calculate_lookthrough_exposure(
    snapshot: PortfolioSnapshot,
    bucket: str,
    *,
    fallback_to_line_item: bool = True,
) -> dict[str, float]:
    """Calculate manually supplied look-through exposure for a metadata bucket.

    If a holding has no manual look-through components and fallback is enabled,
    its line-item metadata is used. No external holdings are fetched.
    """

    portfolio_total = _total_base_equity_value(snapshot)
    exposure: dict[str, float] = {}
    if portfolio_total == 0:
        return exposure

    for holding in snapshot.holdings:
        holding_value = calculate_base_market_value(holding)
        if holding_value is None:
            continue

        if holding.lookthrough_components:
            for component in holding.lookthrough_components:
                component_value = holding_value * component.component_weight
                for exposure_bucket in _lookthrough_component_buckets(component, bucket):
                    exposure[exposure_bucket] = exposure.get(exposure_bucket, 0.0) + component_value / portfolio_total
            continue

        if fallback_to_line_item:
            for exposure_bucket in _holding_buckets(holding, bucket):
                exposure[exposure_bucket] = exposure.get(exposure_bucket, 0.0) + holding_value / portfolio_total

    return dict(sorted(exposure.items()))


def calculate_lookthrough_sector_exposure(
    snapshot: PortfolioSnapshot,
    *,
    fallback_to_line_item: bool = True,
) -> dict[str, float]:
    return calculate_lookthrough_exposure(snapshot, "sector", fallback_to_line_item=fallback_to_line_item)


def find_incomplete_valuation_holdings(snapshot: PortfolioSnapshot) -> list[str]:
    return [holding.ticker for holding in snapshot.holdings if calculate_market_value(holding) is None]


def _calculate_bucket_exposure(
    snapshot: PortfolioSnapshot,
    bucket_getter,
    *,
    use_base_value: bool = False,
) -> dict[str, float]:
    portfolio_total = _total_base_equity_value(snapshot) if use_base_value else snapshot.total_equity_value
    exposure: dict[str, float] = {}
    if portfolio_total == 0:
        return exposure

    for holding in snapshot.holdings:
        market_value = calculate_base_market_value(holding) if use_base_value else calculate_market_value(holding)
        if market_value is None:
            continue
        for bucket in bucket_getter(holding):
            if not bucket:
                continue
            exposure[str(bucket)] = exposure.get(str(bucket), 0.0) + market_value / portfolio_total
    return dict(sorted(exposure.items()))


def _total_base_equity_value(snapshot: PortfolioSnapshot) -> float:
    return sum(calculate_base_market_value(holding) or 0.0 for holding in snapshot.holdings) + snapshot.cash


def _leverage_factor(holding: Holding) -> float:
    return holding.leverage_factor or holding.leverage_multiplier


def _issuer_key(holding: Holding) -> str:
    return (
        holding.issuer_canonical_id
        or holding.issuer_name
        or holding.underlying_issuer_name
        or holding.underlying_ticker
        or holding.ticker
    )


def _instrument_type(holding: Holding) -> str:
    return holding.instrument_type or holding.asset_class


def _holding_buckets(holding: Holding, bucket: str) -> list[str]:
    if bucket == "sector":
        return [holding.sector] if holding.sector else []
    if bucket == "industry":
        return [holding.industry] if holding.industry else []
    if bucket == "region":
        return [holding.region] if holding.region else []
    if bucket == "country_of_risk":
        return [holding.country_of_risk] if holding.country_of_risk else []
    if bucket == "issuer":
        return [_issuer_key(holding)]
    if bucket == "theme":
        return holding.theme
    if bucket == "instrument_type":
        return [_instrument_type(holding)]
    if bucket == "currency":
        return [holding.trading_currency or holding.currency]
    raise ValueError(f"unsupported look-through bucket: {bucket}")


def _lookthrough_component_buckets(component, bucket: str) -> list[str]:
    if bucket == "sector":
        return [component.sector] if component.sector else []
    if bucket == "industry":
        return [component.industry] if component.industry else []
    if bucket == "region":
        return [component.region] if component.region else []
    if bucket == "country_of_risk":
        return [component.country_of_risk] if component.country_of_risk else []
    if bucket == "issuer":
        issuer = component.component_issuer_canonical_id or component.component_issuer_name or component.component_ticker
        return [issuer] if issuer else []
    if bucket == "theme":
        return component.theme
    if bucket == "instrument_type":
        return [component.instrument_type] if component.instrument_type else []
    if bucket == "currency":
        return []
    raise ValueError(f"unsupported look-through bucket: {bucket}")

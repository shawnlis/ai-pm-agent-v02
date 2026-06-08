# Portfolio Schema

This module adds a non-invasive portfolio state layer under `src/ai_pm_agent/portfolio/`.
It does not change `ai_pm_agent.py` behavior and does not call external APIs.

## Why This Module Exists

The PM Agent can research companies, score evidence, and write investment memos, but it needs a formal portfolio state before it can reason about portfolio impact, sizing, concentration, leverage-adjusted exposure, theme exposure, and incomplete valuation data.

## Holding

`Holding` represents one security or portfolio line item. It supports ticker, name, market, currency, asset class, quantity, cost basis, current price, market value, themes, risk bucket, leverage multiplier, and notes.

If `market_value` is missing and `current_price` is available, the model computes `quantity * current_price`. If both `market_value` and `current_price` are missing, the holding remains valid but is marked as valuation-incomplete.

`TQQQ` and `SOXL` default to a `3.0` leverage multiplier when no explicit multiplier is provided.

Phase 3B adds optional metadata fields for more realistic holdings:

- `instrument_type`
- `issuer_name`
- `issuer_canonical_id`
- `underlying_issuer_name`
- `underlying_ticker`
- `listing_country`
- `country_of_risk`
- `region`
- `sector`
- `industry`
- `trading_currency`
- `base_currency`
- `fx_rate_to_base`
- `market_value_local`
- `market_value_base`
- `leverage_factor`
- `lookthrough_available`
- `lookthrough_source`
- `lookthrough_components`

These fields are additive. They do not change PM recommendations, research execution, company database behavior, ratings, or actions.

## Local Taxonomy Values

Portfolio metadata taxonomy values are currently local, user-supplied strings.

This applies to:

- `instrument_type`
- `sector`
- `industry`
- `region`
- `country_of_risk`
- `theme`
- `risk_bucket`

Recommended `instrument_type` examples include `stock`, `etf`, `leveraged_etf`, `crypto_etf`, `gds`, `adr`, `cash`, `fund`, `note`, and `other`.

These values are not yet normalized to an external standard such as GICS, BICS, ISO country codes, MSCI regions, broker taxonomies, or data-provider classifications. Future normalization should be additive and backward compatible: existing local strings should remain valid, and any provider-standard mapping should live beside them rather than replacing them silently.

## PortfolioSnapshot

`PortfolioSnapshot` is a point-in-time view of holdings plus cash. It computes:

- Total holding market value
- Total cash
- Total equity value
- Gross exposure
- Leverage-adjusted exposure
- Holding weights
- Theme exposure
- Asset class exposure
- Currency exposure
- Risk bucket exposure
- Sector exposure
- Industry exposure
- Region exposure
- Country-of-risk exposure
- Issuer exposure
- Instrument-type exposure
- Base-currency holding weights
- Incomplete valuation holdings

## Leveraged ETFs

Leveraged ETFs need leverage-adjusted exposure because their account market value understates their economic exposure. A 10% TQQQ position is roughly 30% Nasdaq exposure before fees, path dependency, and daily reset effects.

`leverage_factor` is accepted as additive metadata and feeds the same calculation path as `leverage_multiplier` when supplied.

Leverage-adjusted gross exposure is a deterministic notional-style reporting helper based on supplied market value and supplied leverage factor. It is not VaR, stress loss, margin requirement, risk-adjusted exposure, beta-adjusted exposure, or portfolio risk advice.

## Issuer And Listing Metadata

Foreign listings, ADRs, GDS lines, and local listings can be grouped with `issuer_canonical_id`.

For example, an ADR line and a Hong Kong local listing can both use the same canonical issuer key so exposure helpers can summarize issuer-level concentration without changing the original tickers.

`market`, `listing_country`, `country_of_risk`, and `region` are intentionally separate:

- `market` identifies where the security trades.
- `listing_country` identifies the listing venue country.
- `country_of_risk` captures the economic issuer risk.
- `region` provides a broader geographic bucket.

## FX And Base-Currency Values

The schema supports manually supplied FX normalization through `market_value_local`, `fx_rate_to_base`, and `market_value_base`.

No FX rates are fetched. If base-currency exposure is used, the caller must supply fake, fixture, or locally approved FX inputs.

Exposure helpers treat supplied base values as user-provided inputs, not market-verified data.

Current fallback behavior:

- `market_value_base` is used when supplied.
- If `market_value_base` is missing and both `market_value_local` and `fx_rate_to_base` are supplied, base value is computed as `market_value_local * fx_rate_to_base`.
- If base fields are missing, base-value helpers fall back to the holding's regular `market_value`.
- If `market_value` is missing and `current_price` is supplied, the holding model computes `quantity * current_price`.
- `PortfolioSnapshot.cash` is treated as already being in `PortfolioSnapshot.base_currency`; multi-currency cash is not modeled yet.

These fallbacks make local fixtures convenient, but they do not certify that values are live, current, or FX-normalized.

For mixed-currency reporting, currency exposure should be weighted by base market value rather than raw local-currency units. The Phase 3C offline input runner reports `Currency Exposure by Base Market Value` and excludes non-base-currency rows that lack a safe base value.

## Manual Look-Through

`LookThroughComponent` supports manually supplied look-through metadata for ETFs, funds, crypto ETFs, or index-like instruments.

Allowed:

- manual component issuer
- manual component ticker
- manual component weight
- manual component sector
- manual component country of risk
- manual component region
- manual component theme tags
- source notes

Not allowed in this module:

- auto-fetching ETF constituents
- live market data
- yfinance calls
- LLM calls
- broker sync
- external provider look-through

If no manual look-through exists, look-through helpers can fall back to line-item metadata. Original line-item exposure remains separate from manual look-through exposure.

If manual look-through components are supplied for a holding, the helper uses only those supplied components for that holding's look-through view. Component residuals are not inferred automatically. If components sum to less than 100%, the unmodeled residual is omitted unless the caller supplies a residual component. If components sum above 100%, the helper does not rebalance them; the caller is responsible for supplying coherent manual weights.

## ETHA Classification

`ETHA` should be treated as crypto ETF / digital asset beta. It is not AI equity exposure even if it can be part of a broader technology portfolio.

## Fixture Usage

`build_sample_portfolio_snapshot()` returns fake test data for TQQQ, SOXL, NVDA, SK Hynix proxy / HY9H / 7709.HK, MU, GOOGL, MSFT, TSLA, ETHA, SMS, and cash.

```python
from ai_pm_agent.portfolio import build_sample_portfolio_snapshot

snapshot = build_sample_portfolio_snapshot()
print(snapshot.leverage_adjusted_exposure)
print(snapshot.theme_exposure)
print(snapshot.sector_exposure)
print(snapshot.issuer_exposure)
```

## Advice Boundary

Exposure output is informational only. Portfolio metadata is not used for suitability advice, trading advice, client advice, PM recommendation changes, rating changes, or action changes.

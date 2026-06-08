# Portfolio Schema

This module adds a non-invasive portfolio state layer under `src/ai_pm_agent/portfolio/`.
It does not change `ai_pm_agent.py` behavior and does not call external APIs.

## Why This Module Exists

The PM Agent can research companies, score evidence, and write investment memos, but it needs a formal portfolio state before it can reason about portfolio impact, sizing, concentration, leverage-adjusted exposure, theme exposure, and incomplete valuation data.

## Holding

`Holding` represents one security or portfolio line item. It supports ticker, name, market, currency, asset class, quantity, cost basis, current price, market value, themes, risk bucket, leverage multiplier, and notes.

If `market_value` is missing and `current_price` is available, the model computes `quantity * current_price`. If both `market_value` and `current_price` are missing, the holding remains valid but is marked as valuation-incomplete.

`TQQQ` and `SOXL` default to a `3.0` leverage multiplier when no explicit multiplier is provided.

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
- Incomplete valuation holdings

## Leveraged ETFs

Leveraged ETFs need leverage-adjusted exposure because their account market value understates their economic exposure. A 10% TQQQ position is roughly 30% Nasdaq exposure before fees, path dependency, and daily reset effects.

## ETHA Classification

`ETHA` should be treated as crypto ETF / digital asset beta. It is not AI equity exposure even if it can be part of a broader technology portfolio.

## Fixture Usage

`build_sample_portfolio_snapshot()` returns fake test data for TQQQ, SOXL, NVDA, SK Hynix proxy / HY9H / 7709.HK, MU, GOOGL, MSFT, TSLA, ETHA, and cash.

```python
from ai_pm_agent.portfolio import build_sample_portfolio_snapshot

snapshot = build_sample_portfolio_snapshot()
print(snapshot.leverage_adjusted_exposure)
print(snapshot.theme_exposure)
```

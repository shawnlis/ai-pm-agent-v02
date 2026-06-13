# Portfolio Risk Cockpit v0.5.0 Phase 1

## Purpose

Portfolio Risk Cockpit v0.5.0 Phase 1 adds a local, offline, review-first risk reporting layer.
It summarizes supplied portfolio fixture rows into deterministic exposure and stress outputs.

This is a risk report, not an investment recommendation.

## Input Schema

Phase 1 accepts CSV fixture input only. The required columns are:

- `ticker`
- `instrument_type`
- `quantity`
- `currency`
- `market_value`
- `notional_value`
- `exposure_multiplier`
- `underlying_ticker`
- `theme`
- `region`
- `notes`

Validation is fail-closed for blank tickers, blank currencies, missing required columns, invalid numeric values, and leveraged ETF rows that do not explicitly show `exposure_multiplier`.

Before reading any file content, Phase 1 refuses real-data-looking paths such as `portfolio.csv`, `IBKR Positions/`, paths containing `ibkr`, broker paths, and client paths.
The guard raises `DISALLOWED_REAL_PORTFOLIO_INPUT` because this phase accepts fixture CSV input only.

Unknown `instrument_type` rows are loaded with `NEEDS_REVIEW` and `UNKNOWN_INSTRUMENT_TYPE`.
Short option rows are loaded with `NEEDS_REVIEW` and `SHORT_OPTION_NEEDS_REVIEW`.

## Output Contracts

Default outputs are written under the ignored reports path:

`reports/portfolio_risk_cockpit/v050/<YYYYMMDD>/`

Required files:

- `PORTFOLIO_RISK_COCKPIT_V050.md`
- `portfolio_risk_summary.json`
- `exposure_by_ticker.csv`
- `exposure_by_theme.csv`
- `exposure_by_currency.csv`
- `stress_scenarios.csv`
- `risk_warnings.md`

The summary JSON includes stable boundary fields showing no broker connection, no trading, no live market data, no LLM, no network access, and no PM prompt wiring.

## Safety Boundaries

- Local/offline fixture CSV input only.
- No IBKR, broker, order, or trading workflow is connected.
- No live market data, yfinance, web search, LLM, OpenRouter, or DeepSeek is used.
- No client data is used.
- `portfolio.csv` is not used.
- IBKR content is not inspected.
- No portfolio data is wired into PM prompts, ratings, actions, or recommendation logic.
- No buy, sell, hold, sizing, rebalance, order, or trade instruction is produced.
- Generated reports, caches, and databases remain local and ignored.

## Stress Scenarios

Phase 1 includes simple deterministic scenario rows:

- Nasdaq -10%
- Semis -15%
- USD/SGD -5%
- ETH/BTC -20%

These are rough risk-impact views based only on supplied row tags, tickers, currencies, and exposure multipliers.
Short-option and unknown-instrument warning codes propagate into affected stress scenario rows, so review-risk positions do not appear clean in stress output.
They are not payoff, margin, greek, VaR, beta, liquidation, tax, suitability, or advice models.

## Known Limitations

- All market values, notionals, currencies, themes, regions, and multipliers are supplied by the fixture input.
- No prices, FX rates, broker statements, option greeks, implied volatility, ETF constituents, or crypto balances are fetched.
- Short options are surfaced for review but are not modeled with greeks, assignment, margin, or scenario-specific payoff curves.
- Currency stress is a placeholder sensitivity, not a full FX translation model.
- Theme matching is local string matching and should be reviewed before relying on the report.

## Why This Is Not Investment Advice

The cockpit reports exposure, concentration, warnings, and simple scenario impacts.
It does not compare securities, rank opportunities, recommend trades, recommend sizing, change PM ratings, or produce client-specific advice.

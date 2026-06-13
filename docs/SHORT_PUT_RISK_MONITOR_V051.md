# Short Put Risk Monitor v0.5.1

## Purpose

Short Put Risk Monitor v0.5.1 adds a local, offline, fixture-only risk report for short put exposures.
It calculates notional exposure, breakeven, distance-to-strike, days-to-expiry, and simple stress impacts from supplied fixture rows.

This is a short put risk report, not an options trading recommendation.

## Input Schema

Phase 1 accepts CSV fixture input only. The required columns are:

- `option_id`
- `underlying_ticker`
- `expiry_date`
- `strike`
- `contracts`
- `contract_multiplier`
- `premium_collected`
- `current_underlying_price`
- `currency`
- `underlying_theme`
- `notes`

Missing required columns, blank core identifiers, and invalid numeric values fail closed.
Blank `expiry_date` is allowed only to produce `MISSING_EXPIRY` and `NEEDS_REVIEW`.
Blank `current_underlying_price` is allowed only to produce `MISSING_UNDERLYING_PRICE` and `NEEDS_REVIEW`.

The loader refuses real-data-looking paths such as `portfolio.csv`, `IBKR Positions/`, paths containing `ibkr`, broker paths, and client paths before reading file contents.

## Output Contracts

Default outputs are written under the ignored reports path:

`reports/short_put_risk_monitor/v051/<YYYYMMDD>/`

Required files:

- `SHORT_PUT_RISK_MONITOR_V051.md`
- `short_put_risk_summary.json`
- `short_put_positions.csv`
- `short_put_stress_scenarios.csv`
- `short_put_warnings.md`

## Warning Definitions

- `MISSING_EXPIRY`: expiry date was blank.
- `EXPIRED_OPTION`: expiry date is before the report as-of date.
- `MISSING_UNDERLYING_PRICE`: current underlying price was blank.
- `NEAR_STRIKE`: current underlying price is within 5% above strike.
- `BELOW_STRIKE`: current underlying price is below strike.
- `BELOW_BREAKEVEN`: current underlying price is below breakeven.
- `LARGE_ASSIGNMENT_NOTIONAL`: assignment notional is at least 100,000 in the supplied currency.
- `NEEDS_REVIEW`: row has one or more review warnings.

## Safety Boundaries

- Fixture CSV input only.
- No broker connection.
- No IBKR content inspection.
- No trading or order placement.
- No roll, close, open, sizing, or rebalance recommendation.
- No live market data, yfinance, web search, LLM, OpenRouter, or DeepSeek.
- No client data.
- No PM prompt or recommendation wiring.
- Generated reports, caches, and databases remain local and ignored.

## Known Limitations

- Stress scenarios are simple intrinsic-value downside checks, not option pricing models.
- `max_simple_downside_at_stress` is floored at zero and should be read as downside after premium, not a full option-pricing model.
- `estimated_pnl_at_stress` is a simple intrinsic-value approximation after premium, not a trade recommendation.
- Positive stress P/L does not mean sell more, hold, roll, or avoid closing.
- Stress output is not payoff, margin, greek, assignment-probability, or advice modeling.
- No greeks, volatility, borrow, early exercise, assignment probability, margin, tax, liquidity, or slippage model is included.
- Missing underlying prices prevent price-derived distance and percentage-down stress calculations.
- All prices, strikes, contracts, multipliers, premiums, themes, and currencies are fixture inputs.
- Currency values are not FX-normalized.

## Why This Is Not Options Advice

The monitor reports risk exposure and warning codes only.
It does not recommend opening, closing, rolling, sizing, hedging, assigning, exercising, or trading options.

# AUTOPM Backtest V01

The autopm backtest harness is deterministic and fixture-only.

It is designed to evaluate whether prior autopm proposal logic can be replayed
without live data, network access, broker access, or order placement.

## Inputs

- fixture-only backtest specification JSON
- fixture-only initial paper portfolio state
- fixture-only historical price series
- optional fixture benchmark series
- precomputed proposal rows or recommendation outcome labels

Every input file must declare `fixture_only=true`. Live-looking paths such as
broker, account, client, statement, IBKR, or `portfolio.csv` fail closed before
file contents are read.

## Behavior

The harness can:

- consume rebalance proposal rows
- simulate portfolio value over time through the paper portfolio engine
- calculate cash, turnover, realized and unrealized PnL
- calculate max drawdown
- calculate hit rate from fixture outcome labels
- compare against a benchmark fixture series
- summarize theme and region exposure

## Boundaries

- no live market data
- no yfinance
- no web or LLM calls
- no broker read
- no broker execution
- no order placement
- no monitor, scheduler, or notification integration

The output is not an investment performance guarantee. Fixture quality
determines result quality.

## No-Lookahead Rule

The backtest rejects fixture rows containing `source_date`, `price_date`,
`available_date`, or `as_of_date` later than the rebalance date being simulated.

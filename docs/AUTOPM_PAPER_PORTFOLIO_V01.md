# AUTOPM Paper Portfolio V01

The autopm paper portfolio harness consumes rebalance proposal rows and fixture
prices to simulate fills locally.

It does not place trades, connect to brokers, read broker accounts, or create
execution artifacts.

## Inputs

- paper portfolio state fixture with `fixture_only=true`
- price fixture with `fixture_only=true`
- rebalance proposal artifact with `not_executed=true`

Every proposal row must also include `not_executed=true`.

## Outputs

Paper state records include:

- cash
- holdings
- portfolio value
- transaction log
- `simulated=true`
- `not_broker_execution=true`

## Boundaries

- proposal rows are simulated only
- missing fixture prices fail closed
- broker/client/account-looking paths fail closed
- no live data
- no yfinance
- no web or LLM calls
- no order placement

The harness is for offline evaluation and shadow-mode review only.

# AUTOPM Local Alpha Safety Checklist V01

Run this checklist before treating `v0.7-autopm-local-alpha` as a release
baseline or before starting read-only live-provider work.

## Mode Boundary

- [ ] `review_first` remains the default mode.
- [ ] `autopm` is explicit opt-in only.
- [ ] Review-first modules do not emit buy/sell/hold/add/trim, sizing,
      target weights, rebalance, orders, or trade instructions.

## Input Boundary

- [ ] Inputs are fixture or explicit local paths.
- [ ] No implicit scan of `reports/` or `outputs/`.
- [ ] No `.env`, `Openrouter.txt`, API keys, tokens, credentials, browser
      sessions, broker credentials, or private files are inspected.
- [ ] No `portfolio.csv`, `IBKR Positions/`, broker, account, client, or
      private portfolio export is used.

## Provider Boundary

- [ ] Level 0 fixture providers pass tests.
- [ ] Any future Level 1 or Level 2 provider is disabled by default.
- [ ] Offline mode blocks live providers.
- [ ] Provider metadata includes source, retrieval time, stale flag, and
      reliability/warning codes.

## Recommendation Boundary

- [ ] Claim audit passes for strict outputs.
- [ ] Output validation passes for strict outputs.
- [ ] Missing valuation blocks buy/add.
- [ ] Stale market data blocks valuation-dependent buy/add.
- [ ] Portfolio concentration breach blocks add.
- [ ] Target weights respect policy caps.
- [ ] High-conviction buy/add has thesis kill triggers.

## Rebalance / Paper Boundary

- [ ] Rebalance rows include `not_executed=true`.
- [ ] Paper portfolio records include `simulated=true`.
- [ ] Paper records include `not_broker_execution=true`.
- [ ] No broker execution artifact exists.
- [ ] No real order placement exists.

## Backtest Boundary

- [ ] Backtest rejects lookahead fields.
- [ ] Backtest fails closed on missing prices.
- [ ] Backtest output is marked simulated and not broker execution.
- [ ] Backtest results are not described as future performance evidence.

## Monitor Boundary

- [ ] Monitor inputs are explicit paths.
- [ ] Monitor does not schedule jobs.
- [ ] Monitor does not send notifications.
- [ ] Critical alerts require manual review only.
- [ ] Critical alerts do not trigger sell, trim, order, broker, scheduler, or
      notification behavior.

## Release Boundary

- [ ] Full pytest passes.
- [ ] Diff contains release docs/tests/fixtures only, plus any minimal README
      note.
- [ ] No generated reports, outputs, caches, databases, or local notes are
      committed.
- [ ] No tag is created before the release-hardening PR is merged.

# Autopm Rebalance Proposal v0.1

## Purpose

The rebalance proposal layer aggregates autopm recommendation rows into a
portfolio-level proposal.

It is proposal-only. It does not place orders, connect to brokers, create
execution artifacts, add CLI commands, or modify review-first modules.

## Proposal Rows

Each proposal row includes:

- ticker
- action
- current weight
- target weight
- delta weight
- estimated notional
- reason codes
- blocked-by codes
- manual review flag
- `not_executed=true`

Blocked or manual-review recommendations remain non-actionable and
`not_executed=true`.

## Portfolio Math

The proposal generator:

- respects max single-name caps
- respects available cash and minimum cash constraints
- allows sells and trims to fund adds only as proposal math
- computes before/after theme, region, sector, issuer, cash, and risk-budget
  summaries
- keeps all rows non-executable

## Boundaries

This layer does not add:

- CLI
- broker read
- broker execution
- order placement
- live data
- network calls
- generated committed reports

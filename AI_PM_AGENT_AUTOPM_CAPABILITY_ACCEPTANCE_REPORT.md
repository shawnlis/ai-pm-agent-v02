# AI PM Agent Autopm Capability Acceptance Report

## Summary Verdict

PR3 adds a machine-checkable acceptance framework for the autopm investment
methodology. It does not add runtime stock picking, recommendations, sizing,
rebalance, broker access, live data, or execution behavior.

## Covered Framework Capabilities

The acceptance matrix covers:

- business model
- unit economics
- growth quality
- moat / competition
- industry cycle
- financial quality
- capital structure
- management / governance
- market expectation gap
- technical / flow signals
- valuation
- thesis kill triggers
- portfolio fit
- Asia AI Hardware bottleneck score
- AI revenue migration
- customer certification / order visibility
- gross margin / FCF quality
- valuation expectation gap

## Covered Fixture Cases

The fixture pack covers:

- high-quality AI bottleneck company with strong evidence and reasonable valuation
- story-only AI company with weak evidence
- sample-stage company
- qualification-stage company
- volume production without material revenue evidence
- strong company missing valuation
- strong company with stale market data
- company with working-capital deterioration
- company blocked by portfolio concentration
- overweight existing holding requiring hold/trim
- thesis-broken holding requiring sell/trim if policy allows

## What Remains Unverified

This PR does not verify:

- actual stock picker scoring quality
- ranking performance
- realized or simulated returns
- portfolio-aware sizing behavior
- rebalance proposal generation
- report generation
- claim audit enforcement
- output validation enforcement
- backtest or paper portfolio performance
- live provider behavior

## Why This Does Not Prove Investment Performance

The acceptance framework verifies representation and safety constraints, not
alpha. It proves that future autopm outputs can be tested for source backing,
gate failures, policy caps, stale data handling, valuation blockers, and
certification-stage semantics.

Investment performance still requires deterministic scoring logic, paper
simulation, backtests, benchmark comparison, hit-rate analysis, drawdown
analysis, and false-positive/false-negative tracking.

## Recommended Next PR

The next PR should add claim audit and output validation. That layer should
enforce the Evidence -> Claim -> Decision path and mark strict-mode output
`INVALID` when source backing, policy consistency, or output consistency fails.

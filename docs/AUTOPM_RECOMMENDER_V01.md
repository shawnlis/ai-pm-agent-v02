# Autopm Recommender v0.1

## Purpose

This PR introduces the first portfolio-aware autopm recommendation layer.

The recommender is explicit autopm-only logic. It may emit PM action labels and
target weights from fixture/local portfolio inputs, stock picker rankings, and
gate results. It does not modify the legacy review-first PM prompt path.

## Inputs

- `StockPickerScore` or compatible ranking output
- explicit local autopm portfolio fixture
- `AutopmPolicy` / `AutopmPortfolioPolicy`
- evidence, valuation, portfolio, risk, and red-team gate results
- source references and source manifest

## Outputs

The recommender emits enriched recommendation rows with:

- ticker, company name, market
- action
- rating
- conviction score
- current, target, and delta weight
- max position
- evidence, valuation, quality, momentum, risk, and portfolio-fit scores
- source-backed reason codes
- risk warnings
- summaries
- thesis kill triggers
- required next evidence
- next review date
- source hashes and source refs
- gate results

## Claim Audit

Recommendation rows are converted into claim-audit-compatible dictionaries.
If strict claim audit fails, the recommender downgrades the row to manual
review rather than returning an invalid trade-style recommendation.

## Boundaries

This PR does not add:

- rebalance proposal generation
- report writer output
- CLI runtime
- backtest or paper portfolio
- live providers
- broker read or execution
- order placement
- legacy PM prompt portfolio wiring

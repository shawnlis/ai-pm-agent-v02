# Autopm Stock Picker v0.1

## Purpose

This document defines the first generic deterministic stock picker layer for
autopm.

The layer is ranking-only. It produces stock picker scores and tiers from
fixture/provider snapshots. It does not produce PM instructions, position
sizing, rebalance rows, portfolio-aware output, broker activity, live data
fetching, web calls, LLM calls, or yfinance calls.

## Inputs

Inputs must be deterministic local objects derived from PR2 provider contracts
or fixture rows. Required identity fields are:

- `ticker`
- `company_name`
- `market`
- `source_hashes`
- `source_refs`

Source metadata gaps are surfaced as `data_gaps` and
`required_next_evidence`.

## Factor Groups

The generic scorer uses these factor groups:

- `business_quality_score`
- `growth_quality_score`
- `earnings_revision_score`
- `valuation_attractiveness_score`
- `momentum_technical_score`
- `balance_sheet_quality_score`
- `evidence_quality_score`
- `catalyst_score`
- `accounting_risk_penalty`
- `crowding_priced_in_risk`

Positive factors are averaged, then accounting and crowding penalties reduce
the total score. All scoring is deterministic and bounded between 0.0 and 1.0.

## Tiers

Ranking tiers are:

- `top_pick`
- `candidate`
- `watchlist`
- `avoid`
- `blocked`

The tier is a research-ranking tier, not a PM instruction.

## Fail-Closed Rules

- Weak evidence caps the score.
- Missing valuation evidence blocks the top tier.
- Stale market data blocks valuation and momentum dependent top-tier ranking.
- Accounting risk can block the top tier.
- Price movement that materially outpaces earnings revisions triggers a
  priced-in risk penalty.
- Missing source metadata creates a data gap and required next evidence.

## Output Boundary

Every stock picker row includes:

- `ticker`
- `company_name`
- `market`
- `rank`
- `total_score`
- `tier`
- `factor_scores`
- `reason_codes`
- `data_gaps`
- `red_flags`
- `required_next_evidence`
- `source_hashes`
- `source_refs`
- `not_recommendation_until_recommender`

The boundary flag marks the row as ranking-only until a later recommender PR
introduces separately audited PM outputs.

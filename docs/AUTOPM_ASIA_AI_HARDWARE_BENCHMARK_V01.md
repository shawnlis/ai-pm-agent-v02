# Autopm Asia AI Hardware Benchmark v0.1

## Purpose

This benchmark checks the Asia AI Hardware strategy against a synthetic,
hand-labeled framework derived from the user's methodology.

It is not a live market-data test and does not assert current facts about real
companies. All rows are synthetic or anonymized fixture cases.

## Fixture Coverage

The benchmark fixture covers:

- CCL/M8/M9 leader
- AI PCB leader
- PPO/HVLP early-stage material company
- optics packaging bottleneck
- high-density connector company
- liquid cooling company
- ODM AI server transition company
- cloud ASIC transition company
- expensive mature leader
- story-only speculative company
- working-capital deteriorating company
- missing valuation company
- stale evidence company
- concentration-risk company
- second-source-risk company

## Expected Labels

Each fixture row can define:

- `expected_tier`
- `expected_min_score`
- `expected_max_score`
- `expected_required_warnings`
- `expected_required_reason_codes`

The benchmark verifies that top-tier overlap meets the configured threshold,
blocked fixture rows do not enter the top tier, required warnings fire, and
ranking is deterministic.

## Boundary

This benchmark is strategy-ranking only. It does not test PM instructions,
position sizing, portfolio-aware behavior, rebalance proposals, broker access,
or live providers.

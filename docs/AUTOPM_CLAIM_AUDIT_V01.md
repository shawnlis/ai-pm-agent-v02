# Autopm Claim Audit v0.1

## Purpose

Claim audit verifies that autopm recommendation-like outputs are source-backed,
internally consistent, and policy-compliant.

This is an accuracy gate only. It does not implement stock picking,
recommendation generation, sizing, rebalance logic, broker reads, broker
execution, live providers, or CLI recommendation workflows.

## Evidence To Decision Contract

Every buy/add/trim/sell-style recommendation must be explainable as:

- action
- reason code
- source hash or policy rule
- evidence level
- source date or `MISSING_SOURCE_DATE` warning
- gate status
- policy cap
- target/current/delta weight consistency

Unsupported high-conviction output must fail closed.

## Checks

`audit_recommendation_claims()` combines:

- `audit_source_manifest_coverage()`
- `audit_policy_consistency()`
- `audit_output_consistency()`

The audit checks:

- every buy/add/trim/sell-style recommendation has reason codes
- every evidence-backed reason code has `source_hash`
- every `source_hash` resolves in the source manifest
- evidence-backed reasons include `evidence_level`
- source date exists unless `MISSING_SOURCE_DATE` is present
- stale evidence cannot support high conviction
- valuation-dependent buy/add requires a valuation snapshot or passed valuation gate
- target weight cannot exceed row or policy cap
- delta weight equals target minus current within tolerance
- buy/add cannot appear if portfolio gate failed
- buy/add cannot appear if valuation gate failed
- high-conviction output requires thesis kill triggers
- severe red-team warnings force manual review/watch/trim/sell/avoid style actions

## Boundaries

Claim audit must not:

- produce recommendations
- fetch live data
- use network access
- inspect secrets
- read broker/account data
- place orders
- emit execution artifacts

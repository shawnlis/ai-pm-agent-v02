# Autopm Output Validation v0.1

## Purpose

The output validator checks whether an autopm run output directory is valid,
invalid, or needs review.

It is local-only. It does not fetch live data, connect to brokers, place
orders, call LLMs, use web search, or call yfinance.

## Command

```powershell
python scripts/autopm_validate_output.py --run-dir <path> --strict
```

## Required Inputs

A run directory must contain:

- `autopm_run_manifest.json`
- `autopm_source_manifest.json`
- `autopm_policy_manifest.json`
- `autopm_recommendations.json` or `autopm_rebalance_proposal.json`

Optional:

- `autopm_claim_audit_summary.json`

## Outputs

The validator writes:

- `AUTOPM_OUTPUT_VALIDATION.md`
- `autopm_output_validation.json`
- `autopm_output_validation.csv`

## Statuses

- `VALID`: no errors or review warnings
- `NEEDS_REVIEW`: no hard errors, but warning-level issues exist
- `INVALID`: hard errors exist

## Checks

The validator checks:

- required files exist
- schema versions match
- source manifest exists
- policy manifest exists
- strict claim audit passed for valid output
- no blocked recommendation appears as executable proposal
- target weights respect policy
- recommendation actions are valid enum values
- source hashes resolve
- severe warnings appear in validation output
- output mode is explicit
- proposal/paper outputs include `not_executed=true`
- no broker/execution/order artifacts exist unless a future execution adapter is explicitly enabled
- unverified strategies cannot enter `live_recommendation` mode

## Boundaries

Output validation is an accuracy gate only. It does not add stock picking,
portfolio-aware recommendations, sizing, rebalance generation, live providers,
broker reads, or broker execution.

# Autopm Report Writer v0.1

## Purpose

The report writer serializes local autopm proposal artifacts into an explicitly
provided output directory.

Tests use temporary directories only. Generated report artifacts are not meant
to be committed.

## Required Human-Facing Outputs

- `AUTOPM_REBALANCE_PROPOSAL.md`
- `autopm_recommendations.csv`
- `autopm_rebalance_proposal.csv`
- `autopm_policy_manifest.json`
- `autopm_risk_warnings.md`

## Validator-Compatible Outputs

The writer also emits validator-compatible local manifests:

- `autopm_run_manifest.json`
- `autopm_source_manifest.json`
- `autopm_recommendations.json`
- `autopm_rebalance_proposal.json`
- `autopm_claim_audit_summary.json`

The PR4 output validator can then classify the run as valid, needs review, or
invalid.

## Boundaries

The writer must not write outside the provided output directory and must not
create broker, execution, or order artifacts.

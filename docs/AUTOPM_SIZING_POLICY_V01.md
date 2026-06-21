# Autopm Sizing Policy v0.1

## Purpose

Autopm sizing converts ranking conviction and gate results into target weights
inside the explicit autopm recommendation layer.

## Sizing Rules

- Target weight cannot exceed `max_single_name_weight_pct`.
- New positions cannot exceed `max_new_position_pct`.
- Adds cannot exceed `max_add_pct_per_run`.
- Weak or failed evidence blocks add-style actions.
- Missing valuation blocks add-style actions.
- Stale market data blocks valuation-dependent add-style actions.
- Portfolio concentration failures block add-style actions.
- Severe red-team warnings force manual review or sell only when policy allows.
- Delta weight must equal target weight minus current weight.

## Portfolio Gates

The portfolio policy layer checks:

- single-name exposure
- theme exposure
- region exposure
- sector exposure
- issuer exposure
- leverage-adjusted exposure
- cash floor

## Loader Boundary

The autopm portfolio loader accepts explicit local fixture/autopm CSV or JSON
files. It rejects real-data-looking path names before reading file contents,
including `portfolio.csv`, IBKR-looking paths, broker-looking paths,
client-looking paths, account-looking paths, and statement-looking paths.

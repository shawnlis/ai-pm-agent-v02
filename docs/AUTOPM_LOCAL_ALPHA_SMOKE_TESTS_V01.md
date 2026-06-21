# AUTOPM Local Alpha Smoke Tests V01

These smoke tests define the local release gate for
`v0.7-autopm-local-alpha`.

## Commands

```powershell
python -m pytest -q tests/test_autopm_local_alpha_release.py
python -m pytest -q
git diff --check origin/master...HEAD
git diff --name-only origin/master...HEAD
```

## Coverage

The smoke test verifies:

- CLI help works.
- CLI `validate-inputs` works on the fixture source pack.
- CLI generic `rank` writes ranking output to a temp directory.
- CLI Asia AI Hardware `rank` writes ranking output to a temp directory.
- `recommend` requires explicit `--mode`.
- `recommend` rejects `live_recommendation`.
- `rebalance` writes proposal artifacts only to a temp directory.
- Rebalance output includes `not_executed=true`.
- Output validator can validate generated tempdir output.
- Backtest rejects lookahead fixtures.
- Paper portfolio requires `not_executed=true`.
- Monitor emits review-trigger alerts only.
- Broker/client/account/IBKR-looking paths are rejected.
- No network access is required.
- No broker/execution imports are introduced.
- No generated output is tracked by Git.

## Passing Standard

Passing this smoke test means the local alpha is usable for fixture-backed
operator review. It does not mean the strategy is predictive, investment advice,
or ready for live provider or broker integration.

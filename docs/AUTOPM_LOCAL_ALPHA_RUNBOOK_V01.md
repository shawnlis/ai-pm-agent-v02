# AUTOPM Local Alpha Runbook V01

This runbook describes the safe local workflow for `v0.7-autopm-local-alpha`.
Use fixture or explicit local paths only.

## Preconditions

- Python dependencies are installed.
- No secrets are required.
- No broker, account, IBKR, or client files are used.
- Output directories are explicit temp or local review directories.
- `review_first` remains the default mode outside explicit autopm commands.

## Workflow

### 1. Validate Inputs

```powershell
python scripts/autopm.py validate-inputs `
  --source-pack tests/fixtures/autopm_cli/source_pack `
  --strategy generic `
  --portfolio tests/fixtures/autopm_cli/sample_autopm_fixture.csv
```

### 2. Rank

Generic:

```powershell
python scripts/autopm.py rank `
  --source-pack tests/fixtures/autopm_cli/source_pack `
  --strategy generic `
  --out-dir .tmp/autopm/rank
```

Asia AI Hardware:

```powershell
python scripts/autopm.py rank `
  --source-pack tests/fixtures/autopm_cli/source_pack `
  --strategy asia_ai_hardware `
  --out-dir .tmp/autopm/asia-rank
```

Ranking output is not a PM recommendation and must not include broker orders.

### 3. Recommend

```powershell
python scripts/autopm.py recommend `
  --source-pack tests/fixtures/autopm_cli/source_pack `
  --portfolio tests/fixtures/autopm_cli/sample_autopm_fixture.csv `
  --mode proposal `
  --out-dir .tmp/autopm/recommend
```

`--mode` is required. `live_recommendation` fails closed in this local alpha.

### 4. Rebalance

```powershell
python scripts/autopm.py rebalance `
  --source-pack tests/fixtures/autopm_cli/source_pack `
  --portfolio tests/fixtures/autopm_cli/sample_autopm_fixture.csv `
  --mode proposal `
  --out-dir .tmp/autopm/rebalance
```

Rebalance output is proposal-only. Every proposal row must preserve
`not_executed=true`.

### 5. Validate Output

```powershell
python scripts/autopm.py validate-output `
  --run-dir .tmp/autopm/rebalance `
  --strict
```

Strict validation must be `VALID` before any output is treated as usable for
human review.

### 6. Backtest

Backtests consume fixture files through the Python harness. They reject
lookahead data and missing required prices.

```powershell
python -m pytest -q tests/test_autopm_backtest.py
```

### 7. Paper Portfolio

Paper portfolio simulation consumes non-executed proposal rows and fixture
prices. It writes simulated records only.

```powershell
python -m pytest -q tests/test_autopm_paper_portfolio.py
```

### 8. Monitor / State Diff

Monitor compares two explicit run directories. It does not scan `reports/` or
`outputs/`.

```powershell
python -m pytest -q tests/test_autopm_monitor.py tests/test_autopm_state_store.py
```

Monitor alerts are review triggers only. Critical alerts do not trigger sell,
trim, order, broker, scheduler, or notification behavior.

## Local Cleanup

Do not commit generated `.tmp/`, `reports/`, `outputs/`, cache, database, or
local review artifacts.

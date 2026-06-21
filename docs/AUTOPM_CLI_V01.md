# AUTOPM CLI V01

`scripts/autopm.py` is an explicit local wrapper around existing autopm
components. It is not a live trading interface.

## Commands

- `validate-inputs`: validates a source pack, optional policy file, and optional
  explicit autopm fixture/local portfolio file.
- `rank`: runs ranking-only generic or Asia AI Hardware stock picker output.
- `recommend`: runs existing portfolio-aware recommender logic from fixture
  inputs and writes recommendation artifacts.
- `rebalance`: consumes recommendation rows or explicit recommendation fixture
  inputs and writes proposal-only rebalance report artifacts.
- `validate-output`: runs the existing output validator against an output
  directory.

## Modes

`recommend` and `rebalance` require `--mode`.

Allowed PR9 execution modes:

- `proposal`
- `paper`

`disabled` and `live_recommendation` fail closed for `recommend` and
`rebalance`. Live execution is not supported. Broker read and broker execution
are not supported.

## Safety Boundaries

- no broker read
- no broker execution
- no live order placement
- no live SEC provider
- no web search
- no yfinance
- no LLM call
- no scheduler
- no monitor
- no backtest or paper portfolio harness

All generated files are written only under an explicit `--out-dir`.
`rebalance` artifacts remain proposal rows with `not_executed=true`.

## Examples

```powershell
python scripts/autopm.py validate-inputs --source-pack tests/fixtures/autopm_cli/source_pack --strategy generic
python scripts/autopm.py rank --source-pack tests/fixtures/autopm_cli/source_pack --strategy generic --out-dir .tmp/autopm/rank
python scripts/autopm.py recommend --source-pack tests/fixtures/autopm_cli/source_pack --portfolio tests/fixtures/autopm_cli/sample_autopm_fixture.csv --mode proposal --out-dir .tmp/autopm/recommend
python scripts/autopm.py rebalance --source-pack tests/fixtures/autopm_cli/source_pack --portfolio tests/fixtures/autopm_cli/sample_autopm_fixture.csv --mode proposal --out-dir .tmp/autopm/rebalance
python scripts/autopm.py validate-output --run-dir .tmp/autopm/rebalance --strict
```

# SEC / IR Evidence Batch Import

## Purpose

The SEC / IR Evidence Batch Import expands Evidence DB coverage for the AI infrastructure universe. It is a read-only source ingestion and export workflow for downstream evidence ledgers and Thesis-Gap Monitor v2.

It is not a recommendation system, portfolio system, trading system, or PM prompt interface.

## AI Infrastructure Universe

`ai_infra_core` currently contains:

- `MU` - Micron Technology
- `NVDA` - NVIDIA
- `AMD` - Advanced Micro Devices
- `AVGO` - Broadcom
- `MSFT` - Microsoft
- `GOOGL` - Alphabet

The batch runner validates requested tickers against this universe. Unknown or duplicate tickers fail closed instead of being silently skipped.

## Input Contracts

Required CLI entrypoint:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py --universe ai_infra_core --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch
```

Supported inputs:

- `--universe ai_infra_core`
- `--companies MU NVDA AMD AVGO MSFT GOOGL`
- `--out-dir <path>`
- `--db <path>`
- `--dry-run`
- `--offline`
- `--export-only`
- `--live-sec-fetch`
- `--sec-user-agent "<Name email@example.com>"`
- `--sec-cache-dir <path>`
- `--force-refresh`
- `--continue-on-company-error`

`--fixture-dir` is available for tests and local fixture development. Fixture files use the names `<TICKER>_submissions_sample.json` and `<TICKER>_companyfacts_sample.json`.

## Output Contracts

The batch output directory contains:

- `batch_manifest.json`
- `batch_warnings.md`
- `company_run_summary.csv`
- `evidence_db.sqlite`
- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`
- `ingestion_warnings.md`

Dry-run mode writes only batch planning outputs and does not create or mutate the Evidence DB.

## Safe Live SEC Fetch Rules

Live SEC access is explicit only:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py `
  --universe ai_infra_core `
  --live-sec-fetch `
  --sec-user-agent "Name email@example.com" `
  --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch
```

Rules:

- No network access occurs unless `--live-sec-fetch` is supplied.
- `--live-sec-fetch` requires `--sec-user-agent`.
- `--offline` blocks `--live-sec-fetch`.
- `--export-only` cannot be combined with `--live-sec-fetch`.
- Company failures are recorded fail-closed with warning codes.
- `--continue-on-company-error` is required to continue after a company failure.

## Dry-Run Examples

Plan the full AI infrastructure universe without imports or network:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py `
  --universe ai_infra_core `
  --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --dry-run
```

Plan a subset:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py `
  --universe ai_infra_core `
  --companies MU NVDA AMD `
  --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --dry-run
```

## Offline / Export-Only Examples

Re-export an existing local Evidence DB without network access:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py `
  --universe ai_infra_core `
  --db .\reports\sec_ir_evidence_db\ai_infra_coverage_batch\evidence_db.sqlite `
  --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --export-only `
  --offline
```

Export-only mode is read-only and does not use network. The batch manifest keeps current-run `network_access` as `false` while preserving source provenance separately through `source_api_level`, `source_fixture_only`, and `source_live_sec_api`. If source provenance cannot be determined from the re-exported manifest or source rows, the batch manifest uses `UNKNOWN` rather than claiming fixture-only provenance.

Run local fixture mode for tests or fixture development:

```powershell
python .\scripts\sec_ir_evidence_batch_import.py `
  --universe ai_infra_core `
  --companies MU `
  --fixture-dir .\tests\fixtures\sec_edgar `
  --out-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --offline
```

## Safety Boundaries

The batch manifest explicitly records:

- `no_portfolio_data: true`
- `no_broker_data: true`
- `no_client_data: true`
- `no_pm_recommendation_wiring: true`
- `no_llm: true`
- `no_yfinance: true`

The batch runner does not inspect `portfolio.csv`, `IBKR Positions/`, broker credentials, client data, `.env`, `Openrouter.txt`, API keys, or token files. It does not call LLMs, OpenRouter, DeepSeek, yfinance, web search, broker APIs, or trading systems.

## Thesis-Gap Monitor v2 Handoff

The batch exports feed Thesis-Gap Monitor v2 through the existing Evidence DB export contracts:

- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`
- `ingestion_warnings.md`

The monitor reads these files as evidence inputs. The batch runner does not wire evidence into PM prompts, produce buy/sell/hold opinions, size positions, or rebalance portfolios.

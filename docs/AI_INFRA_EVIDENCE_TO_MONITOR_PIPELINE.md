# AI Infra Evidence-to-Monitor Pipeline

## Purpose

The AI Infra Evidence-to-Monitor Pipeline chains existing SEC / IR Evidence DB exports into AI Infrastructure Thesis-Gap Monitor v2 outputs. It is a read-only research pipeline for organizing source-backed evidence and monitor outputs.

It is not a recommendation system, portfolio system, trading system, broker workflow, or PM prompt interface.

## Safe Offline-First Flow

Default safe behavior:

- Existing evidence exports can be passed with `--evidence-dir`.
- If only `--evidence-dir` is supplied, the pipeline runs Thesis-Gap Monitor v2 against that existing evidence directory.
- `--run-batch-dry-run` runs batch planning only and does not mutate the Evidence DB.
- No live SEC fetch option is exposed by this pipeline CLI.
- No network access, web search, LLM, yfinance, portfolio, broker, client, or PM recommendation workflow is used.
- Missing evidence fails closed; missing facts are not inferred.

## Input Contracts

Pipeline CLI:

```powershell
python .\scripts\ai_infra_evidence_to_monitor_pipeline.py `
  --evidence-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --monitor-out-dir .\reports\ai_infra_thesis_gap_monitor\v2\pipeline_run `
  --offline
```

Supported flags:

- `--evidence-dir`
- `--batch-out-dir`
- `--monitor-out-dir`
- `--run-batch-dry-run`
- `--run-monitor`
- `--offline`
- `--as-of-date YYYY-MM-DD`
- `--companies MU NVDA AMD AVGO MSFT GOOGL`

The evidence directory must contain the standard Evidence DB export contracts:

- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`
- `ingestion_warnings.md`

## Output Contracts

The pipeline writes:

- `AI_INFRA_PIPELINE_INDEX.json`

When the monitor runs, the monitor output directory also contains:

- `AI_INFRA_THESIS_GAP_MONITOR_V2.md`
- `thesis_gap_table.csv`
- `thesis_gap_summary.json`
- `source_coverage.csv`
- `monitor_warnings.md`

When batch dry-run runs, the batch output directory contains:

- `batch_manifest.json`
- `batch_warnings.md`
- `company_run_summary.csv`

Batch dry-run does not create `evidence_db.sqlite`.

## Batch-to-Monitor Handoff

The batch runner produces Evidence DB export contracts. The monitor reads those contracts as source evidence inputs. This pipeline only coordinates that handoff and writes an index of files created, statuses, warnings, and safety boundaries.

The pipeline does not pass evidence into PM prompts and does not produce buy, sell, hold, sizing, or rebalance instructions.

## Examples

Run the monitor from existing evidence:

```powershell
python .\scripts\ai_infra_evidence_to_monitor_pipeline.py `
  --evidence-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --monitor-out-dir .\reports\ai_infra_thesis_gap_monitor\v2\evidence_pipeline `
  --companies MU NVDA AMD AVGO MSFT GOOGL `
  --as-of-date 2026-06-13 `
  --offline
```

Run batch dry-run only:

```powershell
python .\scripts\ai_infra_evidence_to_monitor_pipeline.py `
  --run-batch-dry-run `
  --batch-out-dir .\reports\sec_ir_evidence_db\ai_infra_pipeline_batch_dry_run `
  --companies MU NVDA AMD AVGO MSFT GOOGL `
  --offline
```

Run batch dry-run and monitor from an existing evidence directory:

```powershell
python .\scripts\ai_infra_evidence_to_monitor_pipeline.py `
  --run-batch-dry-run `
  --run-monitor `
  --evidence-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --batch-out-dir .\reports\sec_ir_evidence_db\ai_infra_pipeline_batch_dry_run `
  --monitor-out-dir .\reports\ai_infra_thesis_gap_monitor\v2\evidence_pipeline `
  --offline
```

## Boundaries

`AI_INFRA_PIPELINE_INDEX.json` records:

- `no_live_sec_fetch: true`
- `no_web_search: true`
- `no_llm: true`
- `no_yfinance: true`
- `no_portfolio_data: true`
- `no_broker_data: true`
- `no_client_data: true`
- `no_pm_recommendation_wiring: true`

Generated outputs belong under ignored `reports/` paths and should not be staged or committed.

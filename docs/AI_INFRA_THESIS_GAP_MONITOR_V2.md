# AI Infrastructure Thesis-Gap Monitor v2

## Purpose

The AI Infrastructure Thesis-Gap Monitor v2 turns existing SEC / IR Evidence Database exports into a conservative source-backed gap report for AI infrastructure themes.

This is a thesis-gap monitor, not an investment recommendation.

The monitor is designed to answer: "What source-backed evidence exists for each thesis gap, what remains unknown, and what needs human review?"

## Input Contracts

The monitor reads existing evidence DB outputs. It does not fetch live sources.

Required inputs can be supplied as an evidence output directory:

```powershell
python .\scripts\ai_infra_thesis_gap_monitor.py `
  --evidence-dir .\reports\sec_ir_evidence_db\live_smoke_mu `
  --out-dir .\reports\ai_infra_thesis_gap_monitor\v2\20260613
```

Or as explicit files:

```powershell
python .\scripts\ai_infra_thesis_gap_monitor.py `
  --ledger-csv .\reports\sec_ir_evidence_db\live_smoke_mu\company_evidence_ledger.csv `
  --metric-history-csv .\reports\sec_ir_evidence_db\live_smoke_mu\metric_history.csv `
  --source-manifest-json .\reports\sec_ir_evidence_db\live_smoke_mu\source_manifest.json `
  --out-dir .\reports\ai_infra_thesis_gap_monitor\v2\20260613
```

Required files:

- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`

Optional files:

- `ingestion_warnings.md`
- `evidence_db.sqlite`

The SQLite database can be present as part of the evidence bundle, but v2 uses the CSV and JSON export contracts as the stable read layer.

## Initial Universe

Default companies:

- `MU`
- `NVDA`
- `AMD`
- `AVGO`
- `MSFT`
- `GOOGL`

Default themes:

- AI capex
- HBM / memory
- GPU / accelerator demand
- networking / ASIC / custom silicon
- cloud infrastructure
- data center margin / capex burden
- supply constraint vs demand slowdown
- customer concentration
- revenue recognition / backlog / deferred revenue

## Output Contracts

Default output path:

`reports/ai_infra_thesis_gap_monitor/v2/<YYYYMMDD>/`

Required outputs:

- `AI_INFRA_THESIS_GAP_MONITOR_V2.md`
- `thesis_gap_table.csv`
- `thesis_gap_summary.json`
- `source_coverage.csv`
- `monitor_warnings.md`

## Gap Schema

Each gap row includes:

- `company`
- `theme`
- `gap_id`
- `gap_question`
- `current_status`
- `evidence_summary`
- `source_count`
- `newest_source_date`
- `confidence`
- `warning_codes`
- `human_review_required`
- `why_it_matters`
- `what_would_close_the_gap`

## Status Definitions

- `CLOSED`: Official source evidence directly closes the gap. This generally requires material revenue, contracted demand, recognized revenue, or equivalent disclosed evidence.
- `PARTIALLY_CLOSED`: Official evidence exists, but it is not enough to prove material revenue or full thesis closure.
- `UNCHANGED`: Relevant source evidence exists, but it does not materially change the gap.
- `WORSENED`: Source evidence points to risk, such as margin pressure, demand slowdown, capex burden, or concentration.
- `UNKNOWN`: Required evidence is missing or not matched to the theme.
- `NEEDS_REVIEW`: Evidence is ambiguous, stale, weak, or requires human interpretation before use.

## Classification Rules

The monitor is deterministic and rule based. It does not call an LLM.

Conservative rules:

- Explicit company filing or official IR evidence can improve a gap.
- Stale evidence weakens confidence.
- Missing evidence stays `UNKNOWN`.
- Ambiguous language stays `NEEDS_REVIEW`.
- Capex growth without monetization evidence is flagged as margin-risk or ROI-risk, not automatically positive.
- Sample evidence does not equal qualification.
- Qualification does not equal volume production.
- Volume production does not equal material revenue.

## Safety Boundaries

The monitor:

- Does not generate buy, sell, hold, sizing, rebalance, or portfolio actions.
- Does not read `portfolio.csv`.
- Does not read IBKR files.
- Does not use broker, account, trading, or client data.
- Does not call LLM/OpenRouter/DeepSeek.
- Does not call yfinance.
- Does not perform web search.
- Does not run live SEC fetches.
- Does not wire evidence into PM prompts or PM recommendation logic.
- Fails closed if required evidence inputs are missing.

## What The Monitor Can Conclude

The monitor can conclude that source-backed evidence is present, stale, missing, ambiguous, risk-indicating, or sufficient to close a defined thesis gap under deterministic rules.

## What The Monitor Cannot Conclude

The monitor cannot conclude that a security should be bought, sold, held, resized, rebalanced, or prioritized. It cannot infer undisclosed metrics, fabricate missing values, or convert weak evidence into investment conclusions.

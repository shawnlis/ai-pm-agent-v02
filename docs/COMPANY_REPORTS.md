# Company DB Reports

Phase 2B adds offline Markdown and CSV report generation on top of `data/company_db/company_research.sqlite`.

Phase 2C adds a refresh planner for deterministic rerun queues. See [REFRESH_PLANNER.md](REFRESH_PLANNER.md).

Phase 2D adds review-only approval packets for human rerun approval. See [APPROVAL_PACKETS.md](APPROVAL_PACKETS.md).

Phase 2G adds the final offline workflow smoke test. See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

Reports are deterministic and rule-based. They do not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs. They only read the SQLite company database and saved artifact metadata already indexed there.

## Safe Entry Point

Use the root-level wrapper:

```powershell
python scripts/company_db_report.py ...
```

Do not rely on `python -m ai_pm_agent...` from the repository root because the top-level `ai_pm_agent.py` shadows the `src/ai_pm_agent` package.

## Report Types

### Company Dossier

Purpose: one ticker's latest decision, chokepoint assessment, market snapshot, evidence, facts, history, warnings, and deterministic refresh checklist.

```powershell
python scripts/company_db_report.py dossier --db data/company_db/company_research.sqlite --ticker GEV --out reports/company_dossiers/GEV.md
```

Batch dossiers:

```powershell
python scripts/company_db_report.py dossier-batch --db data/company_db/company_research.sqlite --tickers GEV,AVGO,KLAC --out-dir reports/company_dossiers
```

### Top Chokepoints

Purpose: rank latest company rows by chokepoint score and show rule-based watchlist observations.

```powershell
python scripts/company_db_report.py top-chokepoints --db data/company_db/company_research.sqlite --limit 25 --out reports/watchlists/top_chokepoints.md
```

CSV sidecar default:

```text
reports/exports/top_chokepoints.csv
```

### Latest Decisions

Purpose: show latest action/rating/score rows and action/rating group counts.

```powershell
python scripts/company_db_report.py latest-decisions --db data/company_db/company_research.sqlite --limit 50 --out reports/watchlists/latest_decisions.md
```

CSV sidecar default:

```text
reports/exports/latest_decisions.csv
```

### Stale / Incomplete

Purpose: identify rows with warnings, missing evidence/facts, or missing parsed tables.

```powershell
python scripts/company_db_report.py stale --db data/company_db/company_research.sqlite --out reports/data_quality/stale_companies.md
```

CSV sidecar default:

```text
reports/exports/stale_companies.csv
```

### Warning Summary

Purpose: summarize import warnings such as missing optional artifacts, unmatched research-log rows, or empty fact JSON.

```powershell
python scripts/company_db_report.py warnings --db data/company_db/company_research.sqlite --out reports/data_quality/warning_summary.md
```

CSV sidecar default:

```text
reports/exports/warning_summary.csv
```

### Decision Changes

Purpose: show tickers with more than one run where action, rating, PM score, or chokepoint score changed.

```powershell
python scripts/company_db_report.py decision-changes --db data/company_db/company_research.sqlite --out reports/watchlists/decision_changes.md
```

CSV sidecar default:

```text
reports/exports/decision_changes.csv
```

## Suggested Workflow Before Live Research

1. Run `latest-decisions` to see the current indexed watchlist.
2. Run `top-chokepoints` to identify high-chokepoint candidates.
3. Run `stale` and `warnings` to separate strong candidates from data-quality problems.
4. Generate dossiers for the most relevant tickers.
5. Only then decide which companies deserve a fresh live research run.
6. Run the refresh planner to create a prioritized approval queue:

```powershell
python scripts/company_db_refresh.py plan --db data/company_db/company_research.sqlite --out reports/refresh/refresh_plan.md --csv reports/refresh/refresh_queue.csv
```
7. Build an approval packet before any live rerun is considered:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --out reports/approval/approval_packet.md --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/manual_rerun_commands.txt --limit 25
```

## Interpreting Warnings

- `missing_optional_artifact`: older runs often predate newer evidence/fact artifacts. Treat this as a data-completeness flag, not an importer failure.
- `research_log_unmatched`: a run folder was indexed, but `outputs/research_log.csv` did not clearly map to it.
- `facts_parse_empty`: a fact JSON artifact existed but did not contain fact records in a recognized list shape.

## Known Limitations

- Reports are only as current as the imported SQLite database.
- No report invents missing valuation, evidence, or fact data.
- Stale/incomplete flags are data-quality flags, not investment conclusions.
- Calendar-age staleness is currently used only for dossier checklist text, not as a database migration or scheduler.
- Approval packets are review-only; they do not execute live research commands.

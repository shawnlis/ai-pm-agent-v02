# Company Research Database

Phase 1 added a local SQLite index for existing AI PM Agent output artifacts. Phase 2A adds read-only query, ranking, history, data-quality, and CSV export commands on top of that index. Phase 2B adds offline Markdown and CSV report generation. It does not change `ai_pm_agent.py` runtime behavior and does not call live LLM, web, yfinance, browser, or external APIs.

Phase 2C adds an offline refresh-candidate planner. See [REFRESH_PLANNER.md](REFRESH_PLANNER.md).

## Purpose

The importer scans existing `outputs/**/pm_decision.json` folders and indexes the local artifacts into:

```text
data/company_db/company_research.sqlite
```

The database is an artifact index, not a replacement for the current research pipeline.

## Entry Points

Because this repository already has a top-level `ai_pm_agent.py`, use the script wrapper from the repository root:

```powershell
python scripts/company_db_import.py import --outputs outputs --db data/company_db/company_research.sqlite --dry-run --limit 5
python scripts/company_db_import.py import --outputs outputs --db data/company_db/company_research.sqlite --limit 5
python scripts/company_db_import.py stats --db data/company_db/company_research.sqlite
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --limit 20
python scripts/company_db_import.py show GEV --db data/company_db/company_research.sqlite
python scripts/company_db_report.py dossier --db data/company_db/company_research.sqlite --ticker GEV --out reports/company_dossiers/GEV.md
python scripts/company_db_refresh.py plan --db data/company_db/company_research.sqlite --out reports/refresh/refresh_plan.md --csv reports/refresh/refresh_queue.csv
```

Direct module execution from the repository root is intentionally not the default because Python resolves the top-level `ai_pm_agent.py` before the `src/ai_pm_agent` package. If module execution is needed later, run it from a working directory that does not contain `ai_pm_agent.py` and place this repository's absolute `src` path on `PYTHONPATH`.

```powershell
$env:PYTHONPATH = "C:\Users\Lenovo\ai_pm_agent_v02\src"
python -m ai_pm_agent.cli.company_db import --outputs C:\Users\Lenovo\ai_pm_agent_v02\outputs --db C:\Users\Lenovo\ai_pm_agent_v02\data\company_db\company_research.sqlite --dry-run --limit 5
```

## Commands

### Import

```powershell
python scripts/company_db_import.py import --outputs outputs --db data/company_db/company_research.sqlite --limit 25
```

Useful flags:

- `--dry-run`: parse and summarize without creating or writing the database.
- `--limit N`: scan at most `N` run folders.
- `--verbose`: print per-run warning details.
- `--outputs PATH`: choose an outputs folder.
- `--db PATH`: choose a SQLite file.

### Validate

```powershell
python scripts/company_db_import.py validate --outputs outputs --db data/company_db/company_research.sqlite --limit 25 --verbose
```

Validation is a dry-run parse pass. It does not write rows.

### List

```powershell
python scripts/company_db_import.py list --db data/company_db/company_research.sqlite --limit 25
```

`list` and `latest` both show the latest decision table:

```text
ticker | company | market | action | rating | pm_score | chokepoint_score | confidence | latest_run_date | warning_count
```

Useful filters:

```powershell
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --ticker GEV
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --market US --action watchlist --rating watch
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --min-chokepoint-score 7 --max-chokepoint-score 10
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --min-pm-score 5 --sort pm_score --desc
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --has-warnings --missing-evidence
```

### Show

```powershell
python scripts/company_db_import.py show GEV --db data/company_db/company_research.sqlite
```

`show` prints ticker history plus the saved PM judgment when present.

### Stats

```powershell
python scripts/company_db_import.py stats --db data/company_db/company_research.sqlite
```

Prints table counts and warning counts by warning type.

### Latest

```powershell
python scripts/company_db_import.py latest --db data/company_db/company_research.sqlite --limit 20
```

Shows the latest indexed decision per ticker.

### History

```powershell
python scripts/company_db_import.py history --db data/company_db/company_research.sqlite --ticker GEV --limit 10
```

History columns:

```text
run_date | action | rating | pm_score | chokepoint_score | suggested_position | artifact_path
```

### Ranking

```powershell
python scripts/company_db_import.py rank --db data/company_db/company_research.sqlite --sort chokepoint_score --desc --limit 20
python scripts/company_db_import.py rank --db data/company_db/company_research.sqlite --sort pm_score --desc --limit 20
```

Ranking columns:

```text
ticker | company | chokepoint_score | evidence_level | action | rating | latest_run_date
```

### Warnings

```powershell
python scripts/company_db_import.py warnings --db data/company_db/company_research.sqlite --limit 50
python scripts/company_db_import.py warnings --db data/company_db/company_research.sqlite --ticker GEV
python scripts/company_db_import.py warnings --db data/company_db/company_research.sqlite --warning-type missing_optional_artifact
```

### Stale / Incomplete

```powershell
python scripts/company_db_import.py stale --db data/company_db/company_research.sqlite --limit 50
```

This is a data-quality view for latest ticker rows with warnings, missing evidence rows, or missing core parsed tables.

### CSV Export

```powershell
python scripts/company_db_import.py export-csv --db data/company_db/company_research.sqlite --out exports/company_db_latest_decisions.csv
```

Export types:

```powershell
python scripts/company_db_import.py export-csv --type latest_decisions --db data/company_db/company_research.sqlite --out exports/company_db_latest_decisions.csv
python scripts/company_db_import.py export-csv --type chokepoint_ranking --db data/company_db/company_research.sqlite --out exports/company_db_chokepoint_ranking.csv
python scripts/company_db_import.py export-csv --type stale --db data/company_db/company_research.sqlite --out exports/company_db_stale.csv
python scripts/company_db_import.py export-csv --type warnings --db data/company_db/company_research.sqlite --out exports/company_db_warnings.csv
```

### Offline Reports

Use `scripts/company_db_report.py` for deterministic Markdown and CSV reports generated only from the SQLite database and indexed saved artifacts.

Single-company dossier:

```powershell
python scripts/company_db_report.py dossier --db data/company_db/company_research.sqlite --ticker GEV --out reports/company_dossiers/GEV.md
```

Batch dossiers:

```powershell
python scripts/company_db_report.py dossier-batch --db data/company_db/company_research.sqlite --tickers GEV,AVGO,KLAC --out-dir reports/company_dossiers
```

Watchlist reports:

```powershell
python scripts/company_db_report.py top-chokepoints --db data/company_db/company_research.sqlite --limit 25 --out reports/watchlists/top_chokepoints.md
python scripts/company_db_report.py latest-decisions --db data/company_db/company_research.sqlite --limit 50 --out reports/watchlists/latest_decisions.md
python scripts/company_db_report.py decision-changes --db data/company_db/company_research.sqlite --out reports/watchlists/decision_changes.md
```

Data-quality reports:

```powershell
python scripts/company_db_report.py stale --db data/company_db/company_research.sqlite --out reports/data_quality/stale_companies.md
python scripts/company_db_report.py warnings --db data/company_db/company_research.sqlite --out reports/data_quality/warning_summary.md
```

Report table CSV sidecars are written under `reports/exports/` by default unless `--csv-out` is supplied.

### Refresh Planner

Use `scripts/company_db_refresh.py` to produce deterministic rerun queues from the SQLite database:

```powershell
python scripts/company_db_refresh.py stats --db data/company_db/company_research.sqlite
python scripts/company_db_refresh.py plan --db data/company_db/company_research.sqlite --out reports/refresh/refresh_plan.md --csv reports/refresh/refresh_queue.csv
python scripts/company_db_refresh.py queue --db data/company_db/company_research.sqlite --queue urgent_refresh --out reports/refresh/urgent_refresh.md --csv reports/refresh/urgent_refresh.csv
python scripts/company_db_refresh.py explain --db data/company_db/company_research.sqlite --ticker GEV
```

The refresh planner does not execute reruns. Suggested commands are templates for human review only.

### Approval Packets

Use `scripts/company_db_approval.py` to convert refresh candidates into a review-only approval packet and editable manifest:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --out reports/approval/approval_packet.md --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/manual_rerun_commands.txt --limit 25
python scripts/company_db_approval.py build-urgent --db data/company_db/company_research.sqlite --out reports/approval/urgent_approval_packet.md --manifest reports/approval/urgent_approval_manifest.csv --commands-out reports/approval/urgent_manual_rerun_commands.txt
python scripts/company_db_approval.py explain-packet --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv
```

Approval packets do not execute reruns. They are offline, deterministic review packets with blank approval fields for human review. See [APPROVAL_PACKETS.md](APPROVAL_PACKETS.md).

Validate a manually edited manifest and extract review-only approved command templates:

```powershell
python scripts/company_db_approval.py validate --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approval_validation.md --csv reports/approval/approval_validation.csv
python scripts/company_db_approval.py extract-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/approved_commands.txt --manifest-out reports/approval/approved_manifest_validated.csv --validation-out reports/approval/approval_validation.md
python scripts/company_db_approval.py dry-run-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approved_dry_run.md
```

Approval validation still does not execute reruns. See [APPROVAL_VALIDATION.md](APPROVAL_VALIDATION.md).

Run the final Phase 2 offline workflow smoke test:

```powershell
python scripts/company_db_smoke_test.py --db data/company_db/company_research.sqlite --outputs outputs --report reports/workflow/offline_smoke_test_report.md --json reports/workflow/offline_smoke_test_summary.json
```

See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

## Indexed Artifacts

Run folders are discovered by locating:

```text
outputs/**/pm_decision.json
```

The importer records known sibling artifacts when present:

- `pm_decision.json`
- `market_snapshot.json`
- `quality_report.md`
- `market_snapshot.md`
- `evidence_context.md`
- `fact_cache_report_before.json`
- `fact_cache_report_before.md`
- `fact_cache_report_after.json`
- `fact_cache_report_after.md`
- `cached_facts_used.json`
- `fresh_facts.json`

It also associates `outputs/research_log.csv` rows when the row clearly points to the run folder.

## Tables

The Phase 1 schema creates:

- `schema_migrations`
- `companies`
- `tickers`
- `research_runs`
- `market_snapshots`
- `evidence_items`
- `facts`
- `chokepoint_assessments`
- `pm_decisions`
- `artifact_files`
- `import_warnings`

Raw JSON is preserved for `pm_decisions`, `market_snapshots`, and facts so future migrations can recover fields not mapped in Phase 1.

## Safety Notes

- The importer reads only local artifact files under the selected outputs directory.
- It does not read `.env`, `Openrouter.txt`, browser profiles, tokens, keys, or credentials.
- Missing optional artifacts create `import_warnings` rows instead of stopping the import.
- Malformed JSON creates `import_warnings` rows and skips the affected parsed table while still indexing the run folder.
- Re-imports are idempotent through deterministic IDs and SQLite upserts.
- Query commands are read-only against the SQLite database except for `export-csv`, which writes the requested CSV file.
- Report commands are read-only against the SQLite database except for writing requested Markdown/CSV outputs.
- Refresh planner commands are read-only against the SQLite database except for writing requested Markdown/CSV queue outputs.
- Approval packet commands are read-only against the SQLite database except for writing requested Markdown/CSV/text review outputs.
- Approval validation commands are read-only against the SQLite database except for writing requested validation, manifest, and command-template outputs.
- The offline smoke test runs only existing offline wrapper scripts and does not execute `ai_pm_agent.py`.
- This is still an offline artifact index, report generator, refresh planner, and approval workflow, not a live research platform, dashboard, scheduler, or advisor copilot.

## Tests

```powershell
python -m unittest tests.test_company_db
```

The tests use temporary directories and do not touch production outputs or the production database.

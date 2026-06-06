# Offline Workflow Smoke Test

Phase 2G adds the final offline smoke test for the company research database workflow.

The smoke test verifies that the existing offline tools can run from artifact import through manual runbook generation. It does not execute `ai_pm_agent.py`, does not run research refresh commands, and does not call live APIs.

## Purpose

- Verify the Phase 2 offline workflow end to end.
- Confirm wrapper scripts still work from the repository root.
- Confirm the SQLite database has required nonzero table counts.
- Confirm generated Markdown, CSV, TXT, and JSON outputs exist and are non-empty.
- Confirm zero-approved approval manifests are handled cleanly.

## Safe Entry Point

```powershell
python scripts/company_db_smoke_test.py --db data/company_db/company_research.sqlite --outputs outputs --report reports/workflow/offline_smoke_test_report.md --json reports/workflow/offline_smoke_test_summary.json
```

## Workflow Covered

The smoke test runs these existing offline entrypoints:

- `scripts/company_db_import.py import`
- `scripts/company_db_import.py stats`
- `scripts/company_db_import.py latest`
- `scripts/company_db_import.py rank`
- `scripts/company_db_report.py dossier`
- `scripts/company_db_report.py top-chokepoints`
- `scripts/company_db_report.py latest-decisions`
- `scripts/company_db_report.py stale`
- `scripts/company_db_report.py warnings`
- `scripts/company_db_report.py decision-changes`
- `scripts/company_db_refresh.py plan`
- `scripts/company_db_approval.py build`
- `scripts/company_db_approval.py validate`
- `scripts/company_db_approval.py extract-approved`
- `scripts/company_db_approval.py build-runbook`

If `GEV` or `AVGO` is unavailable, the smoke test chooses available tickers from the database and records the substitution in the report.

## Outputs

```text
reports/workflow/offline_smoke_test_report.md
reports/workflow/offline_smoke_test_summary.json
```

The smoke test also validates existing generated artifacts under:

```text
reports/company_dossiers/
reports/watchlists/
reports/data_quality/
reports/exports/
reports/refresh/
reports/approval/
```

## Pass Criteria

- Offline wrapper commands return exit code `0`.
- Required DB tables have nonzero counts:
  - `companies`
  - `research_runs`
  - `pm_decisions`
  - `chokepoint_assessments`
- Expected output files exist and are non-empty.
- Approval extraction handles zero approved rows without failure.
- Manual runbook generation succeeds.

## Failure Handling

If any step fails, do not proceed to Phase 3. Fix the failed offline workflow step first.

If all steps pass, Phase 2 should stop here. Use the system manually before considering Phase 3.

## Safety Limitations

- The smoke test is offline QA only.
- It does not execute research refresh commands.
- It does not call `ai_pm_agent.py`.
- It does not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs.
- It does not guarantee future live API availability or research quality.

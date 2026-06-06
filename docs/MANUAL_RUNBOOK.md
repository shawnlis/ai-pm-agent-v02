# Manual Runbook

Phase 2F adds an offline manual runbook generator for approved research refresh commands.

The runbook is a human-review execution plan. It reads the validated manifest, the approved command-template file, and the SQLite company database, then writes a Markdown runbook and CSV step list. It does not execute commands.

Phase 2G adds the final offline workflow smoke test. See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

## Purpose

- Turn validated approved rows into a manual execution plan.
- Group valid approved commands into batches.
- Provide pre-run and post-run safety checklists.
- Preserve excluded invalid or ambiguous rows for review.
- Produce a CSV step list for tracking manual progress.

## Inputs

```text
reports/approval/approved_manifest_validated.csv
reports/approval/approved_commands.txt
data/company_db/company_research.sqlite
```

## Outputs

```text
reports/approval/manual_runbook.md
reports/approval/manual_runbook_steps.csv
```

## Example Command

```powershell
python scripts/company_db_approval.py build-runbook --db data/company_db/company_research.sqlite --validated-manifest reports/approval/approved_manifest_validated.csv --commands reports/approval/approved_commands.txt --out reports/approval/manual_runbook.md --csv reports/approval/manual_runbook_steps.csv
```

Use a custom batch size:

```powershell
python scripts/company_db_approval.py build-runbook --db data/company_db/company_research.sqlite --validated-manifest reports/approval/approved_manifest_validated.csv --commands reports/approval/approved_commands.txt --out reports/approval/manual_runbook.md --csv reports/approval/manual_runbook_steps.csv --batch-size 5
```

## How To Use The Runbook

1. Edit `approval_manifest.csv` manually.
2. Run approval validation.
3. Run approved-command extraction.
4. Build the manual runbook.
5. Review the pre-run checklist.
6. Manually copy commands only after a separate live-run approval.
7. Use `manual_runbook_steps.csv` to track manual progress.
8. Run post-run offline import and report regeneration after live refreshes complete.

## Zero-Approved Behavior

If there are no `valid_approved` rows, the generator still writes both output files. The Markdown clearly states that no commands are approved for execution, and the CSV contains headers with zero command rows.

## What It Does Not Do

- It does not execute `ai_pm_agent.py`.
- It does not call subprocess.
- It does not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs.
- It does not schedule reruns.
- It does not modify `ai_pm_agent.py`.

## Safety Limitations

- The runbook is only as current as the validated manifest and SQLite database.
- Command syntax remains template-based and must be reviewed.
- The tool cannot guarantee API availability, cost, runtime, or research quality.
- A human must manually approve and manually run any live research refresh.

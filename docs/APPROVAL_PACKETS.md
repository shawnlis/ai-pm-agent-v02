# Approval Packets

Phase 2D adds offline approval packets for refresh candidates.

Approval packets are review packages for a human to inspect before any live research reruns. They read `data/company_db/company_research.sqlite` through the refresh planner, select candidate tickers, and write Markdown, CSV, and command-template outputs.

Phase 2E adds approval-manifest validation and approved-command extraction. See [APPROVAL_VALIDATION.md](APPROVAL_VALIDATION.md).

Phase 2F adds a manual runbook for validated approved commands. See [MANUAL_RUNBOOK.md](MANUAL_RUNBOOK.md).

Phase 2G adds the final offline workflow smoke test. See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

## What They Do

- Summarize the current refresh queue.
- Include urgent and high-priority candidates.
- Add concise company review cards.
- Group candidate reasons by deterministic reason code.
- Write a manifest CSV with a blank `approved` column for manual review.
- Write manual rerun command templates.

## What They Do Not Do

- They do not execute reruns.
- They do not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs.
- They do not parse generated Markdown reports as primary input.
- They do not schedule or approve work automatically.
- They do not modify `ai_pm_agent.py`.

## Safe Entry Point

Use the root-level wrapper:

```powershell
python scripts/company_db_approval.py ...
```

Do not rely on `python -m ai_pm_agent...` from the repository root because the top-level `ai_pm_agent.py` shadows the `src/ai_pm_agent` package.

## Example Commands

Build the default packet:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --out reports/approval/approval_packet.md --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/manual_rerun_commands.txt --limit 25
```

Build only urgent candidates:

```powershell
python scripts/company_db_approval.py build-urgent --db data/company_db/company_research.sqlite --out reports/approval/urgent_approval_packet.md --manifest reports/approval/urgent_approval_manifest.csv --commands-out reports/approval/urgent_manual_rerun_commands.txt
```

Build only high-priority candidates:

```powershell
python scripts/company_db_approval.py build-high-priority --db data/company_db/company_research.sqlite --out reports/approval/high_priority_approval_packet.md --manifest reports/approval/high_priority_approval_manifest.csv --commands-out reports/approval/high_priority_manual_rerun_commands.txt
```

Explain a generated manifest:

```powershell
python scripts/company_db_approval.py explain-packet --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv
```

## Filters

The `build` command supports:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --queue urgent_refresh --min-score 80 --tickers GEV,AVGO --out reports/approval/filtered_packet.md --manifest reports/approval/filtered_manifest.csv
```

Useful filters:

- `--queue`
- `--min-score`
- `--limit`
- `--ticker`
- `--tickers`
- `--include-monitor-only`
- `--exclude-no-refresh-needed`

`no_refresh_needed` rows are excluded from approval packets by default.

## Output Files

Default outputs:

```text
reports/approval/approval_packet.md
reports/approval/approval_manifest.csv
reports/approval/manual_rerun_commands.txt
```

Queue-specific outputs:

```text
reports/approval/urgent_approval_packet.md
reports/approval/urgent_approval_manifest.csv
reports/approval/urgent_manual_rerun_commands.txt
reports/approval/high_priority_approval_packet.md
reports/approval/high_priority_approval_manifest.csv
reports/approval/high_priority_manual_rerun_commands.txt
```

## Reviewing The Manifest

The manifest contains one row per selected ticker. The `approved` column is blank by default. Edit it manually after reviewing each row.

Important columns:

- `approved`
- `ticker`
- `company`
- `market`
- `queue`
- `refresh_score`
- `reason_codes`
- `suggested_manual_command`
- `notes`

Do not treat a row as approved until a human has checked ticker, market, company name, reason codes, and live-run permission.

Accepted `approved` values:

```text
true
yes
y
1
approve
approved
x
```

Not-approved values:

```text
empty
false
no
n
0
```

Ambiguous values such as `maybe`, `later`, `partial`, or `unsure` are reported as validation warnings and excluded.

## Validation And Extraction

Validate a manually edited manifest:

```powershell
python scripts/company_db_approval.py validate --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approval_validation.md --csv reports/approval/approval_validation.csv
```

Extract validated approved command templates:

```powershell
python scripts/company_db_approval.py extract-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/approved_commands.txt --manifest-out reports/approval/approved_manifest_validated.csv --validation-out reports/approval/approval_validation.md
```

Generate a dry-run report:

```powershell
python scripts/company_db_approval.py dry-run-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approved_dry_run.md
```

Build a manual runbook:

```powershell
python scripts/company_db_approval.py build-runbook --db data/company_db/company_research.sqlite --validated-manifest reports/approval/approved_manifest_validated.csv --commands reports/approval/approved_commands.txt --out reports/approval/manual_runbook.md --csv reports/approval/manual_runbook_steps.csv
```

These commands do not execute reruns. They only validate rows and write review outputs.

## Safe Workflow Before Live Reruns

1. Generate the refresh plan.
2. Build the approval packet.
3. Review urgent candidates first.
4. Edit `approved` manually in the manifest.
5. Run `validate`.
6. Run `extract-approved`.
7. Build `manual_runbook.md`.
8. Review `approved_commands.txt` and `manual_runbook.md`.
9. Confirm whether live LLM, web, and yfinance calls are allowed.
10. Confirm output overwrite policy.
11. Run approved commands manually in a separate phase.

## Limitations

- Approval packets are only as current as the SQLite database.
- They do not verify current market prices, evidence freshness, or external availability.
- Suggested commands are conservative templates and may need argument checks.
- Generated Markdown reports are not used as source-of-truth input.
- A human must approve every live research run.
- Validation and extraction still do not run live research commands.
- The manual runbook is a review document only and does not execute commands.

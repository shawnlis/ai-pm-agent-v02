# Approval Validation

Phase 2E adds an offline validator for manually edited approval manifests.

The validator reads `reports/approval/approval_manifest.csv`, checks approved rows against `data/company_db/company_research.sqlite`, and writes review-only outputs. It does not execute any command templates.

Phase 2F adds a manual runbook generated from validated approved rows. See [MANUAL_RUNBOOK.md](MANUAL_RUNBOOK.md).

Phase 2G adds the final offline workflow smoke test. See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

## Purpose

- Validate human-approved manifest rows.
- Detect ambiguous approval values.
- Check ticker, company, queue, score, reason-code, and command-template fields.
- Reject approved rows with unsafe command patterns.
- Extract valid approved command templates into a review file.

## What This Phase Does Not Do

- It does not run `ai_pm_agent.py`.
- It does not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs.
- It does not schedule reruns.
- It does not auto-approve rows.
- It does not modify `ai_pm_agent.py`.

## Accepted Approval Values

The `approved` column accepts these values as approved:

```text
true
yes
y
1
approve
approved
x
```

These values are treated as not approved:

```text
empty
false
no
n
0
```

Unexpected values such as `maybe`, `later`, `partial`, or `unsure` are classified as `ambiguous_approval`.

## Validation Rules

Approved rows must include:

- `ticker`
- `company`
- `queue`
- `refresh_score`
- `reason_codes`
- `suggested_manual_command`

Approved rows are checked for:

- ticker exists in the SQLite database
- company name roughly matches the database company name
- queue is one of `urgent_refresh`, `high_priority`, `normal_refresh`, `monitor_only`, `no_refresh_needed`
- refresh score is numeric and between 0 and 100
- suggested command is present
- suggested command avoids unsafe shell operators and risky command names

Company mismatch is a warning. Missing required fields, unknown tickers, invalid queues, invalid scores, and dangerous command patterns are errors.

## Command Safety Checks

The validator rejects dangerous command patterns outside quoted text and outside trailing comments, including:

- shell chaining operators such as `&`, `&&`, `|`, `||`, `;`, and `<`
- command substitution such as backticks and `$()`
- `powershell`
- `cmd /c`
- deletion or system commands such as `del`, `erase`, `rm`, `rmdir`, `format`, and `shutdown`
- network helpers such as `curl`, `wget`, `Invoke-WebRequest`, and `iwr`
- `Start-Process`

Quoted company names and Windows paths are allowed when they do not introduce shell operators outside quotes.

## Example Workflow

1. Generate an approval packet:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --out reports/approval/approval_packet.md --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/manual_rerun_commands.txt --limit 25
```

2. Manually edit `reports/approval/approval_manifest.csv` and mark approved rows.

3. Validate the manifest:

```powershell
python scripts/company_db_approval.py validate --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approval_validation.md --csv reports/approval/approval_validation.csv
```

4. Extract validated approved command templates:

```powershell
python scripts/company_db_approval.py extract-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/approved_commands.txt --manifest-out reports/approval/approved_manifest_validated.csv --validation-out reports/approval/approval_validation.md
```

5. Generate a dry-run report:

```powershell
python scripts/company_db_approval.py dry-run-approved --db data/company_db/company_research.sqlite --manifest reports/approval/approval_manifest.csv --out reports/approval/approved_dry_run.md
```

6. Build the manual runbook:

```powershell
python scripts/company_db_approval.py build-runbook --db data/company_db/company_research.sqlite --validated-manifest reports/approval/approved_manifest_validated.csv --commands reports/approval/approved_commands.txt --out reports/approval/manual_runbook.md --csv reports/approval/manual_runbook_steps.csv
```

## Output Files

```text
reports/approval/approval_validation.md
reports/approval/approval_validation.csv
reports/approval/approved_commands.txt
reports/approval/approved_manifest_validated.csv
reports/approval/approved_dry_run.md
reports/approval/manual_runbook.md
reports/approval/manual_runbook_steps.csv
```

## Interpreting Status Values

- `valid_approved`: approved row passed validation and can be reviewed in `approved_commands.txt`
- `invalid_approved`: approved row failed validation and was excluded
- `ambiguous_approval`: approval value was not understood and was excluded
- `not_approved`: row was not approved and was excluded

## Safety Limitations

- Validation is deterministic but conservative.
- The command syntax is not guaranteed to be perfect for a future live run.
- The validator cannot confirm external service availability.
- The manual runbook is still review-only and does not run commands.
- A separate human approval is still required before running any live research.

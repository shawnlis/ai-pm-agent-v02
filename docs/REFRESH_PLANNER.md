# Refresh Planner

Phase 2C adds an offline refresh-candidate planner for the company research database.

Phase 2D adds approval packets that convert refresh candidates into human-review packages before any live rerun. See [APPROVAL_PACKETS.md](APPROVAL_PACKETS.md).

Phase 2G adds the final offline workflow smoke test. See [OFFLINE_WORKFLOW_SMOKE_TEST.md](OFFLINE_WORKFLOW_SMOKE_TEST.md).

The planner answers:

- Which companies should be rerun next?
- Why should they be rerun?
- Which queue should they go into?
- What is the suggested priority?
- What manual command template should a human review later?

It reads `data/company_db/company_research.sqlite` as the source of truth. It does not parse generated Markdown reports as primary input.

## What It Does Not Do

- It does not execute live research.
- It does not call LLMs, web search, yfinance, brokers, Telegram, Hyatt, or external APIs.
- It does not schedule reruns.
- It does not modify `ai_pm_agent.py`.
- It does not approve or launch suggested commands.
- It does not replace the Phase 2D approval packet review step.

## Safe Entry Point

Use the root-level wrapper:

```powershell
python scripts/company_db_refresh.py ...
```

Do not rely on `python -m ai_pm_agent...` from the repository root because the top-level `ai_pm_agent.py` shadows the `src/ai_pm_agent` package.

## Commands

Generate the full plan:

```powershell
python scripts/company_db_refresh.py plan --db data/company_db/company_research.sqlite --out reports/refresh/refresh_plan.md --csv reports/refresh/refresh_queue.csv
```

Generate one queue:

```powershell
python scripts/company_db_refresh.py queue --db data/company_db/company_research.sqlite --queue urgent_refresh --out reports/refresh/urgent_refresh.md --csv reports/refresh/urgent_refresh.csv
python scripts/company_db_refresh.py queue --db data/company_db/company_research.sqlite --queue high_priority --out reports/refresh/high_priority.md --csv reports/refresh/high_priority.csv
```

Explain one ticker:

```powershell
python scripts/company_db_refresh.py explain --db data/company_db/company_research.sqlite --ticker GEV
```

Print queue stats:

```powershell
python scripts/company_db_refresh.py stats --db data/company_db/company_research.sqlite
```

## Scoring Rules

Refresh score is deterministic and capped at 100.

Staleness:

- latest run older than 30 days: `+30`
- latest run older than 14 days: `+20`
- latest run older than 7 days: `+10`
- missing latest run date: `+25`

Data completeness:

- no PM decision: `+40`
- no market snapshot: `+20`
- no chokepoint assessment: `+25`
- zero evidence items: `+20`
- zero facts: `+15`
- warning count 1-2: `+5`
- warning count 3-5: `+10`
- warning count 6 or more: `+15`

Investment relevance:

- chokepoint score >= 9: `+20`
- chokepoint score >= 8: `+15`
- PM score >= 7: `+15`
- action indicates buy/add/accumulate/starter/tracking: `+15`
- action indicates monitor/watchlist/watch: `+8`
- other action value present: `+5`

Confidence and quality:

- confidence <= 1: `+15`
- confidence <= 2: `+10`
- confidence missing: `+5`
- evidence level missing or weak: `+10`
- high chokepoint score and confidence <= 2: `+15`
- high chokepoint score and evidence items < 5: `+15`
- PM score and chokepoint score diverge by at least 3: `+10`

Change detection:

- latest action changed from prior indexed run: `+15`
- latest rating changed from prior indexed run: `+15`
- PM score changed by at least 1.0: `+10`
- chokepoint score changed by at least 1.0: `+10`

## Queue Definitions

- `urgent_refresh`: score >= 80, missing core parsed data, or high-chokepoint quality issue.
- `high_priority`: score 60-79.
- `normal_refresh`: score 35-59.
- `monitor_only`: score 15-34.
- `no_refresh_needed`: score < 15.

## Output Files

Full plan:

```text
reports/refresh/refresh_plan.md
reports/refresh/refresh_queue.csv
```

Queue exports:

```text
reports/refresh/urgent_refresh.md
reports/refresh/urgent_refresh.csv
reports/refresh/high_priority.md
reports/refresh/high_priority.csv
```

Approval packet outputs:

```text
reports/approval/approval_packet.md
reports/approval/approval_manifest.csv
reports/approval/manual_rerun_commands.txt
```

## Interpreting The Plan

Use `urgent_refresh` and `high_priority` as review queues, not automatic execution queues. The suggested manual commands are templates only. They should be reviewed for ticker, company name, market, and run parameters before any live research is approved.

## Recommended Human Approval Workflow

1. Run `stats`.
2. Generate `refresh_plan.md`.
3. Review `urgent_refresh` and `high_priority`.
4. Run `explain` for any ticker whose score looks surprising.
5. Compare with the company dossier if needed.
6. Build an approval packet:

```powershell
python scripts/company_db_approval.py build --db data/company_db/company_research.sqlite --out reports/approval/approval_packet.md --manifest reports/approval/approval_manifest.csv --commands-out reports/approval/manual_rerun_commands.txt --limit 25
```

7. Manually approve and run live research separately.

## Limitations

- The planner is only as current as the SQLite database.
- It does not verify current market data or current external evidence.
- It does not parse Markdown reports as input.
- It does not know whether a live rerun would be rate-limited or blocked.
- The scoring is deterministic but heuristic.
- Approval packets are still offline review artifacts and do not execute reruns.

# Alpha Source Pack Importer v0.1

## Purpose

The Alpha Source Pack importer reads an explicit Alpha Research Team export
directory and converts reviewed source-pack records into local review queues.

It is a `review_first` bridge. It does not connect AI PM Agent to Alpha Research
Team, autopm, brokers, live providers, portfolio files, private account data, or
execution systems.

## Allowed Input

The importer accepts exactly one explicit input directory:

```powershell
python scripts\import_alpha_source_pack.py --source-pack <path-to-alpha-source-pack>
```

The directory must contain only the Alpha Source Pack files:

- `manifest.json`
- `reviewed_signals.jsonl`
- `theme_candidates.jsonl`
- `evidence_manifest.jsonl`
- `quality_audit.csv`
- `outcomes.jsonl`
- `red_team_summary.md`
- `rejected_noise_summary.md`

The importer fails closed if the pack is missing files, has unexpected files,
contains raw HTML, contains environment or credential file names, includes path
traversal, or if any required file resolves outside the source-pack directory.

## Review-First Mapping

Imported records map only to review states:

- Reviewed `Watch` items map to `WATCHLIST_ONLY` or `EVIDENCE_BLOCKED`.
- Reviewed `Incubating` items with a passing quality audit map to
  `THESIS_IMPROVING` or `CATALYST_MONITOR`.
- Missing evidence, quality-audit issues, overclaiming, or draft candidate
  status maps to `EVIDENCE_BLOCKED`.
- Rejected/noise records map to `DO_NOT_USE`.

These states are research queue states only. They are not PM ratings, allocation
fields, portfolio deltas, execution requests, or model prompts.

## Explicit Exclusions

The importer must not read or require:

- `.env`
- `Openrouter.txt`
- credentials, keys, tokens, or browser sessions
- broker or private account data
- `IBKR Positions/`
- portfolio files
- generated `outputs/` or `reports/` trees outside the explicit source-pack path
- raw SEC HTML or fetched payload directories

The importer preserves source provenance from `evidence_manifest.jsonl` but does
not ingest raw evidence text.

## Output

The CLI writes:

```text
alpha_source_pack_review.md
```

The report includes:

- imported signals
- imported candidates
- evidence quality
- missing evidence
- red-team objections
- what would improve or weaken the research case
- explicit review-first boundary flags

The report must not contain PM action language, allocation language, execution
language, or portfolio fields.

## Boundary

Hard boundary values are emitted with every import:

```json
{
  "mode": "review_first",
  "autopm_enabled": false,
  "portfolio_context_used": false,
  "broker_connection": false,
  "execution_enabled": false,
  "pm_decision_engine": false
}
```

This importer does not enable autopm. A future integration would need a separate
PR, separate policy review, and separate tests.

# AI Infrastructure Opportunity Discovery

## Purpose

AI Infrastructure Opportunity Discovery creates a deterministic review queue from existing local SEC / IR Evidence Database exports and AI Infrastructure Thesis-Gap Monitor outputs.

The layer identifies companies where source-backed evidence is improving, gaps are closing, or catalyst evidence is becoming more visible. It is a discovery layer, not a stock picker and not a recommendation engine.

## Boundaries

- No investment recommendation output.
- No PM prompt wiring.
- No portfolio, IBKR, broker, or client data.
- No order placement or trading workflow.
- No LLM, web search, yfinance, or live market-data calls.
- No new live SEC fetches.

## Inputs

Required Evidence DB artifacts:

- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`

Required thesis-gap monitor artifacts:

- `thesis_gap_table.csv`
- `thesis_gap_summary.json`
- `source_coverage.csv`
- `monitor_warnings.md`

Optional tracking and risk artifacts:

- previous `opportunity_scorecard.json`
- previous `opportunity_candidates.csv`
- local risk warning summary CSV, JSON, or Markdown

Optional risk inputs are read-only and path-guarded. The loader rejects obvious portfolio, IBKR, broker, or client-looking paths before reading contents.

## Outputs

Default outputs are written under ignored `reports/` paths:

- `AI_INFRA_OPPORTUNITY_REVIEW_QUEUE.md`
- `opportunity_candidates.csv`
- `opportunity_scorecard.json`
- `opportunity_warnings.md`
- `opportunity_discovery_manifest.json`
- `opportunity_delta_summary.csv`
- `opportunity_transition_report.md`

## Scoring Method

Each company receives deterministic component scores:

- `evidence_strength_score`
- `gap_closure_score`
- `source_freshness_score`
- `catalyst_signal_score`
- `valuation_data_availability_score`
- `risk_blocker_penalty`
- `missing_data_penalty`

Source coverage, dated evidence, valuation-data availability, and risk warnings act as gates. Strong evidence with missing valuation data is classified as thesis-improving or valuation-blocked, not upgraded to review-candidate status.

v0.6.1 adds prior-run delta fields:

- `prior_status`
- `current_status`
- `status_change`
- `score_delta`
- `newly_promoted`
- `newly_downgraded`
- `unchanged`

Every candidate also includes:

- `why_this_status`
- `what_would_upgrade`
- `what_would_downgrade`
- `unresolved_blockers`
- `required_next_evidence`
- `not_investment_advice`

## Statuses

- `OPPORTUNITY_REVIEW`: source coverage and valuation data are present, risk warnings are absent, and the deterministic score clears the review threshold.
- `THESIS_IMPROVING`: thesis evidence is improving, but valuation or other review inputs are not complete.
- `CATALYST_MONITOR`: catalyst evidence is visible but not enough for review-candidate status.
- `VALUATION_BLOCKED`: valuation data is missing.
- `EVIDENCE_BLOCKED`: source coverage is weak, stale, or undated.
- `RISK_BLOCKED`: risk warnings require review before opportunity work.
- `WATCHLIST_ONLY`: the company remains in the queue for evidence monitoring only.
- `DO_NOT_USE`: reserved for invalid future inputs.

## Discovery vs IC Readiness

Discovery status only means a company deserves structured review. IC readiness still requires valuation work, risk review, source verification, and separate human approval.

## Limitations

- The discovery queue uses deterministic rules only.
- The discovery queue depends on existing local artifacts.
- Valuation availability is a data-presence gate, not a valuation judgment.
- Prior-run history supports status and score deltas, but does not infer investment merit.

## Next Steps

- Add explicit valuation artifact ingestion once a reviewed valuation export contract exists.
- Add source-level catalyst taxonomy after more evidence DB history exists.

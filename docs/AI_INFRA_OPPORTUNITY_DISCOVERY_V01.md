# AI Infrastructure Opportunity Discovery v0.1

## Purpose

AI Infrastructure Opportunity Discovery v0.1 creates a deterministic review queue from existing local SEC / IR Evidence Database exports and AI Infrastructure Thesis-Gap Monitor outputs.

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

## Outputs

Default outputs are written under ignored `reports/` paths:

- `AI_INFRA_OPPORTUNITY_REVIEW_QUEUE.md`
- `opportunity_candidates.csv`
- `opportunity_scorecard.json`
- `opportunity_warnings.md`
- `opportunity_discovery_manifest.json`

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

- v0.1 uses deterministic rules only.
- v0.1 depends on existing local artifacts.
- Valuation availability is a data-presence gate, not a valuation judgment.
- Prior-week history is accepted for manifest tracking but not yet used for trend deltas.

## Next Steps

- Add prior-run delta scoring.
- Add explicit valuation artifact ingestion once a reviewed valuation export contract exists.
- Add source-level catalyst taxonomy after more evidence DB history exists.

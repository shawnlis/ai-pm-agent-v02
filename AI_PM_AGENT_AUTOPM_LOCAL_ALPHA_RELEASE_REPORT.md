# AI PM Agent Autopm Local Alpha Release Report

## Summary Verdict

`v0.7-autopm-local-alpha` is ready for release-hardening review once this PR's
smoke tests and full pytest pass. The baseline is local-only and fixture-backed.
It does not add live data, broker read, broker execution, scheduler, or
notification behavior.

## Included Baseline

- dual-mode `review_first` / `autopm` contract
- autopm schemas, policy, data contracts, and fixture providers
- capability acceptance tests
- claim audit and output validation gates
- generic and Asia AI Hardware ranking
- portfolio-aware recommendations and sizing
- rebalance proposal and report writer
- explicit local CLI wrapper
- deterministic backtest and paper portfolio harness
- explicit-path monitor and state-diff alert artifacts

## Release Gates

- Claim audit must pass for strict valid output.
- Output validation must pass for strict valid output.
- Proposal rows must remain `not_executed=true`.
- Paper portfolio records must remain `simulated=true`.
- Backtests must reject lookahead inputs.
- Critical monitor alerts require manual review only.

## Known Limitations

- Fixture quality limits output quality.
- Deterministic scoring is not predictive proof.
- Backtests are not evidence of future performance.
- Paper fills are simulated.
- No broker execution exists.
- No live provider is included in this release-hardening PR.

## Recommended Next Phase

After this PR is merged and full pytest passes on clean master, create the
annotated tag:

```powershell
git tag -a v0.7-autopm-local-alpha -m "v0.7 autopm local alpha"
git push origin v0.7-autopm-local-alpha
```

Only after the tag should the project consider a PR for a read-only live
provider boundary. Broker execution should remain out of scope until a separate
future adapter is explicitly designed, tested, configured, and approved.

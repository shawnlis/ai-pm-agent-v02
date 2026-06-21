# AI PM Agent

AI PM Agent is a Python research workflow for public-company analysis, source-backed evidence tracking, PM decision logging, offline company database reporting, portfolio exposure review, and AI infrastructure thesis monitoring.

The project is a review-first research system by default. It is not a trading bot, broker workflow, or client-advice system.

## Dual-Mode Direction

AI PM Agent is moving toward a dual-mode architecture:

- `review_first`: the default mode for evidence organization, research queues, gap monitoring, risk reporting, and approval packets. It must not output buy/sell/hold/add/trim, target weights, sizing, rebalances, orders, or trade instructions.
- `autopm`: an explicit opt-in mode for future stock picker rankings, PM recommendations, target weights, and rebalance proposals. Autopm outputs are allowed only when enabled by command, config, or test fixture.

Broker execution remains disabled unless a future execution adapter is explicitly implemented, tested, configured, and enabled. See `docs/AUTOPM_MODE_V01.md` for the mode contract.

## Autopm Local Alpha

`v0.7-autopm-local-alpha` is the local-only autopm baseline for fixture-backed
ranking, recommendation, rebalance proposal, output validation, backtest, paper
portfolio, and monitor smoke testing. It does not add live data, broker read,
broker execution, scheduler, notifications, or investment performance
guarantees. See `docs/AUTOPM_LOCAL_ALPHA_V0_7.md` and
`docs/AUTOPM_LOCAL_ALPHA_RUNBOOK_V01.md`.

## Canonical Workspace

Use this checkout:

```powershell
C:\Users\Lenovo\ai_pm_agent_v02
```

Do not use `C:\Users\Lenovo\Documents\AI PM Agent` for this project. That path was an accidental empty checkout location and is not the repository of record.

GitHub remote:

```powershell
https://github.com/shawnlis/ai-pm-agent-v02.git
```

## Current Stage

The repository is past the original v0.3 README state.

- Current `master` baseline: `v0.6.1-private-opportunity-discovery-hardening`.
- Recent completed work: PR `#18 [codex] Harden AI infra opportunity discovery transitions`, which updated AI Infrastructure Opportunity Discovery to schema `v0.6.1`.
- Architecture track: Phase 4A characterized the legacy `ai_pm_agent.py` monolith. The next architecture step is Phase 4B prompt-builder extraction, and it should be a separate PR.

## Repository Map

- `ai_pm_agent.py`: legacy monolithic CLI and live research workflow entrypoint.
- `src/ai_pm_agent/company_db/`: local SQLite artifact index, query, ranking, and report helpers.
- `src/ai_pm_agent/approval/`: review-only approval manifests, validation, command extraction, and manual runbooks.
- `src/ai_pm_agent/portfolio/`: local portfolio schema, fixture helpers, exposure calculations, and offline IBKR statement import staging.
- `src/ai_pm_agent/portfolio_risk_cockpit/`: local/offline portfolio risk report from fixture inputs.
- `src/ai_pm_agent/short_put_risk_monitor/`: local/offline short-put exposure monitor from fixture inputs.
- `src/ai_pm_agent/evidence_db/`: SEC / IR evidence ledger, source manifests, fixture imports, and explicit Level 1 public SEC fetch adapter.
- `src/ai_pm_agent/thesis_gap_monitor/`: deterministic AI infrastructure thesis-gap monitor.
- `src/ai_pm_agent/ai_infra_pipeline/`: evidence-to-monitor handoff pipeline.
- `src/ai_pm_agent/opportunity_discovery/`: deterministic AI infrastructure opportunity review queue.
- `src/ai_pm_agent/risk_cockpit_pipeline/`: local risk cockpit handoff and fixture market-data pipeline.
- `docs/`: module contracts, safety boundaries, and operator runbooks.
- `tests/`: deterministic unit and boundary tests.
- `examples/`: small fixture inputs only.

## Python Version

Use Python 3.11 or newer. GitHub CI currently runs Python 3.11.

## Setup

Create a virtual environment and install runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development and tests:

```powershell
python -m pip install -r requirements-dev.txt
```

## Environment Variables

Copy `.env.example` to `.env` for local use:

```powershell
Copy-Item .env.example .env
```

Fill in local API keys only in `.env`. Do not commit `.env`, `Openrouter.txt`, credentials, tokens, browser sessions, caches, generated outputs, SQLite databases, broker files, or private portfolio exports.

Basic CLI help and unit tests do not require real API keys.

## Core Commands

Legacy CLI help:

```powershell
python ai_pm_agent.py --help
```

The legacy CLI exposes:

- `single`
- `batch`
- `log`
- `scout`
- `abtest-chokepoint`
- `validate`

Avoid live research workflows unless credentials, output paths, and human approval are intentionally configured.

Opportunity discovery is an offline review queue:

```powershell
python .\scripts\ai_infra_opportunity_discovery.py `
  --evidence-dir .\reports\sec_ir_evidence_db\ai_infra_coverage_batch `
  --monitor-dir .\reports\ai_infra_thesis_gap_monitor\v2\evidence_pipeline `
  --offline
```

The opportunity-discovery output is not investment advice. `OPPORTUNITY_REVIEW` means structured human review is warranted; it does not mean buy, sell, hold, size, rebalance, or trade.

## Tests

Run the full test suite:

```powershell
python -m pytest -q
```

Useful focused checks:

```powershell
python -m pytest -q tests\test_ai_infra_opportunity_discovery.py
python -m pytest -q tests\test_portfolio_recommendation_boundary.py
python -m pytest -q tests\test_phase4a_monolith_characterization.py
```

The test suite should run without API keys.

## Safety Boundaries

- No broker connection, order placement, trading, rebalancing, or money movement.
- No portfolio, IBKR, broker, client, or account data may enter PM prompts, PM recommendations, ratings, target prices, or action decisions.
- Portfolio and risk modules are descriptive review layers only.
- Opportunity discovery is a deterministic research review queue only.
- SEC Level 1 live fetches are public, read-only, explicit opt-in, and blocked by `--offline`.
- Generated outputs belong under ignored local paths such as `outputs/`, `reports/`, caches, and SQLite databases.
- Do not inspect or print secrets, tokens, `.env`, `Openrouter.txt`, private keys, browser state, or broker credentials.

## Local Outputs

Generated outputs are local-only and ignored by Git. Common locations include:

- `outputs/`
- `reports/`
- `data/fact_cache/`
- `data/company_db/company_research.sqlite`

The committed file `data/company_db/company_research_schema.sql` is schema-only. See `data/company_db/README_LOCAL_DB.md` for local database handling.

## Agent And Handoff Notes

Some local worktrees may include untracked `AGENTS.md` or `HANDOFF.md` files for agent operating rules and continuation state. Treat them as local handoff artifacts unless they are intentionally reviewed and added in a documentation PR.

## Intentionally Not Tracked

The `.gitignore` excludes local secrets and generated/private artifacts, including:

- `.env`, `.env.*`
- `Openrouter.txt`
- `secrets/`, `credentials/`, cookies, sessions, browser state
- `outputs/`, `reports/`, `diagnostics/`, logs, caches, archives
- `data/fact_cache/`
- SQLite/database files and model artifacts
- virtual environments and Python caches

Keep private client data, broker files, portfolio exports, and generated research outputs outside Git.

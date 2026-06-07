# AI PM Agent v0.3

AI PM Agent is a Python research workflow for public-company analysis, PM decision logging, chokepoint scouting, company database import/reporting, and approval-packet generation. The repository contains source code, docs, tests, templates, and schema-only database assets. Local secrets, generated research outputs, caches, and private SQLite databases are intentionally not tracked.

## Python Version

Use Python 3.11 or newer. The current clean-clone sanity checks were run with Python 3.13.

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

Fill in local API keys only in `.env`. Do not commit `.env`, `Openrouter.txt`, credentials, tokens, browser sessions, caches, generated outputs, or SQLite databases.

Basic CLI help and unit tests do not require real API keys.

## CLI Help

```powershell
python ai_pm_agent.py --help
```

The main CLI exposes these command groups:

- `single`
- `batch`
- `log`
- `scout`
- `abtest-chokepoint`
- `validate`

Avoid running live research workflows unless local credentials and output locations are configured.

## Tests

```powershell
python -m pytest
```

The test suite focuses on local company database behavior and offline workflow logic. It should run without API keys.

## Local Outputs

Generated outputs are local-only and ignored by Git. Common locations include:

- `outputs/`
- `reports/`
- `data/fact_cache/`
- `data/company_db/company_research.sqlite`

The committed file `data/company_db/company_research_schema.sql` is schema-only. See `data/company_db/README_LOCAL_DB.md` for local database handling.

## Intentionally Not Tracked

The `.gitignore` excludes local secrets and generated/private artifacts, including:

- `.env`, `.env.*`
- `Openrouter.txt`
- `secrets/`, `credentials/`, cookies, sessions, browser state
- `outputs/`, `reports/`, `diagnostics/`, logs, caches, archives
- `data/fact_cache/`
- SQLite/database files and model artifacts
- virtual environments and Python caches

Keep private client data and generated research outputs outside Git.

from __future__ import annotations

import ast
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.evidence_db import http_client
from ai_pm_agent.evidence_db.batch_runner import (
    AI_INFRA_CORE_UNIVERSE,
    COMPANY_SUMMARY_FIELDS,
    DEFAULT_BATCH_OUTPUT_DIR,
    WARNING_BATCH_FIXTURE_MISSING,
    WARNING_BATCH_NOT_RUN_AFTER_FAILURE,
    FixturePaths,
    generate_batch_plan,
    run_batch,
)
from ai_pm_agent.evidence_db.http_client import HttpJsonResponse
from ai_pm_agent.evidence_db.sec_edgar import import_live_sec
from ai_pm_agent.evidence_db.warnings import MISSING_FACT_VALUE


SCRIPT = ROOT / "scripts" / "sec_ir_evidence_batch_import.py"
SUBMISSIONS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_submissions_sample.json"
COMPANYFACTS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_companyfacts_sample.json"

EXPECTED_MANIFEST_KEYS = {
    "api_level",
    "cache_used",
    "companies_completed",
    "companies_failed",
    "companies_requested",
    "continue_on_company_error",
    "dry_run",
    "export_only",
    "fixture_only",
    "force_refresh",
    "generated_at",
    "global_evidence_warning_codes",
    "live_sec_api",
    "network_access",
    "no_broker_data",
    "no_client_data",
    "no_llm",
    "no_pm_recommendation_wiring",
    "no_portfolio_data",
    "no_yfinance",
    "per_company_output_status",
    "run_id",
    "source_api_level",
    "source_fixture_only",
    "source_live_sec_api",
    "standard_outputs",
    "universe",
    "warning_codes",
    "warnings",
}


def test_dry_run_batch_plan_generates_expected_six_companies() -> None:
    plan = generate_batch_plan(universe=AI_INFRA_CORE_UNIVERSE, dry_run=True)

    assert [company.ticker for company in plan.companies] == ["MU", "NVDA", "AMD", "AVGO", "MSFT", "GOOGL"]
    assert plan.network_access is False


def test_offline_mode_blocks_live_sec_fetch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--universe",
                AI_INFRA_CORE_UNIVERSE,
                "--live-sec-fetch",
                "--sec-user-agent",
                "Unit Test unit@example.com",
                "--offline",
                "--out-dir",
                str(Path(tmp) / "out"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "--offline blocks --live-sec-fetch" in result.stderr


def test_missing_sec_user_agent_blocks_live_sec_fetch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--universe",
                AI_INFRA_CORE_UNIVERSE,
                "--live-sec-fetch",
                "--out-dir",
                str(Path(tmp) / "out"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "--live-sec-fetch requires --sec-user-agent" in result.stderr


def test_one_company_failure_is_recorded_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU", "NVDA"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair()},
            continue_on_company_error=True,
        )

    manifest = result["manifest"]
    nvda_rows = [row for row in manifest["per_company_output_status"] if row["ticker"] == "NVDA"]
    assert nvda_rows[0]["status"] == "failed"
    assert WARNING_BATCH_FIXTURE_MISSING in nvda_rows[0]["warning_codes"]
    assert "NVDA" in manifest["companies_failed"]


def test_continue_on_company_error_continues_safely() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU", "NVDA", "AMD"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair(), "AMD": _fixture_pair()},
            continue_on_company_error=True,
        )

    statuses = {row["ticker"]: row["status"] for row in result["manifest"]["per_company_output_status"]}
    assert statuses == {"MU": "completed", "NVDA": "failed", "AMD": "completed"}


def test_without_continue_on_company_error_stops_safely() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU", "NVDA", "AMD"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair(), "AMD": _fixture_pair()},
            continue_on_company_error=False,
        )

    statuses = {row["ticker"]: row["status"] for row in result["manifest"]["per_company_output_status"]}
    amd_row = [row for row in result["manifest"]["per_company_output_status"] if row["ticker"] == "AMD"][0]
    assert statuses == {"MU": "completed", "NVDA": "failed", "AMD": "not_run"}
    assert WARNING_BATCH_NOT_RUN_AFTER_FAILURE in amd_row["warning_codes"]


def test_batch_manifest_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair()},
        )
        manifest_path = Path(result["outputs"]["batch_manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert set(manifest) == EXPECTED_MANIFEST_KEYS
    assert manifest["no_portfolio_data"] is True
    assert manifest["no_broker_data"] is True
    assert manifest["no_client_data"] is True
    assert manifest["no_pm_recommendation_wiring"] is True
    assert manifest["no_llm"] is True
    assert manifest["no_yfinance"] is True


def test_export_only_preserves_live_source_provenance(monkeypatch) -> None:
    submissions_payload = json.loads(SUBMISSIONS_FIXTURE.read_text(encoding="utf-8"))
    companyfacts_payload = json.loads(COMPANYFACTS_FIXTURE.read_text(encoding="utf-8"))

    def fake_fetch(url: str, user_agent: str):
        if "companyfacts" in url:
            return _response(url, companyfacts_payload)
        return _response(url, submissions_payload)

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        live_db = tmp_path / "live" / "evidence_db.sqlite"
        import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent="Unit Test unit@example.com",
            cik="723125",
            out_dir=tmp_path / "live",
            db_path=live_db,
            cache_dir=tmp_path / "cache",
        )

        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU"],
            db_path=live_db,
            out_dir=tmp_path / "export",
            export_only=True,
            offline=True,
        )
        batch_manifest = result["manifest"]
        source_manifest = json.loads((tmp_path / "export" / "source_manifest.json").read_text(encoding="utf-8"))

    assert batch_manifest["network_access"] is False
    assert batch_manifest["source_api_level"] == "Level 1"
    assert batch_manifest["source_fixture_only"] is False
    assert batch_manifest["source_live_sec_api"] is True
    assert batch_manifest["fixture_only"] is False
    assert batch_manifest["live_sec_api"] is True
    assert source_manifest["network_access"] is False
    assert source_manifest["api_level"] == "Level 1"
    assert source_manifest["fixture_only"] is False
    assert source_manifest["live_sec_api"] is True


def test_company_warning_codes_are_not_polluted_by_global_warning_codes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bad_companyfacts = _companyfacts_missing_value(tmp_path / "MU_companyfacts_bad.json")
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU", "AMD"],
            out_dir=tmp_path / "out",
            fixture_paths={
                "MU": FixturePaths(submissions_fixture=SUBMISSIONS_FIXTURE, companyfacts_fixture=bad_companyfacts),
                "AMD": _fixture_pair(),
            },
            continue_on_company_error=True,
        )

    rows = {row["ticker"]: row for row in result["manifest"]["per_company_output_status"]}
    assert MISSING_FACT_VALUE in rows["MU"]["warning_codes"]
    assert MISSING_FACT_VALUE not in rows["AMD"]["warning_codes"]
    assert MISSING_FACT_VALUE in result["manifest"]["global_evidence_warning_codes"]


def test_company_summary_csv_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair()},
        )
        rows = _read_csv(Path(result["outputs"]["company_run_summary"]))

    assert list(rows[0]) == COMPANY_SUMMARY_FIELDS


def test_no_network_by_default(monkeypatch) -> None:
    def fail_fetch(*args, **kwargs):
        raise AssertionError("batch fixture/default mode must not call HTTP")

    monkeypatch.setattr(http_client, "fetch_json", fail_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        result = run_batch(
            universe=AI_INFRA_CORE_UNIVERSE,
            companies=["MU"],
            out_dir=Path(tmp) / "out",
            fixture_paths={"MU": _fixture_pair()},
        )

    assert result["status"] == "completed"


def test_no_forbidden_data_source_or_recommendation_imports_or_calls() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "evidence_db" / "batch_runner.py",
        SCRIPT,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    imported_modules = set()
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_imports = {
        "ai_pm_agent.portfolio",
        "yfinance",
        "requests",
        "openai",
        "ib_insync",
    }
    assert forbidden_imports.isdisjoint(imported_modules)
    forbidden_call_markers = [
        "portfolio.csv",
        "IBKR Positions",
        "build_pm_prompt",
        "run_company_research",
        "call_llm",
        "OpenRouter",
        "DeepSeek",
        "place_order",
        "submit_order",
    ]
    for marker in forbidden_call_markers:
        assert marker not in combined


def test_generated_outputs_default_under_ignored_reports_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert DEFAULT_BATCH_OUTPUT_DIR.parts[0] == "reports"
    assert "reports/" in gitignore


def test_cli_dry_run_writes_batch_plan_without_standard_import_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--universe",
                AI_INFRA_CORE_UNIVERSE,
                "--out-dir",
                str(out_dir),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert (out_dir / "batch_manifest.json").exists()
        assert not (out_dir / "evidence_db.sqlite").exists()


def _fixture_pair() -> FixturePaths:
    return FixturePaths(submissions_fixture=SUBMISSIONS_FIXTURE, companyfacts_fixture=COMPANYFACTS_FIXTURE)


def _companyfacts_missing_value(path: Path) -> Path:
    payload = json.loads(COMPANYFACTS_FIXTURE.read_text(encoding="utf-8"))
    payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0].pop("val")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _response(url: str, payload: object) -> HttpJsonResponse:
    raw_text = json.dumps(payload, sort_keys=True)
    return HttpJsonResponse(
        url=url,
        payload=payload,
        raw_text=raw_text,
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        retrieved_at="2026-06-13T00:00:00+00:00",
        status_code=200,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

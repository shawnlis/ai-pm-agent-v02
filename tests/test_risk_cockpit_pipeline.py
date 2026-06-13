from __future__ import annotations

import ast
import csv
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.risk_cockpit_pipeline.fixture_market_data import (
    FixtureMarketDataProvider,
    load_fixture_market_data,
)
from ai_pm_agent.risk_cockpit_pipeline.models import (
    RiskCockpitPipelineError,
    RiskCockpitPipelineFailure,
    assert_safe_input_path,
)
from ai_pm_agent.risk_cockpit_pipeline.report_writer import default_output_dir
from ai_pm_agent.risk_cockpit_pipeline.runner import run_pipeline
from ai_pm_agent.risk_cockpit_pipeline.schema import (
    ARTIFACT_SUMMARY_FIELDS,
    ARTIFACT_SUMMARY_FILENAME,
    ENRICHMENT_SUMMARY_FIELDS,
    ENRICHMENT_SUMMARY_FILENAME,
    INDEX_FILENAME,
    MARKET_DATA_SNAPSHOT_FIELDS,
    MARKET_DATA_SNAPSHOT_FILENAME,
    REPORT_FILENAME,
    WARNING_SUMMARY_FIELDS,
    WARNING_SUMMARY_FILENAME,
    WARNINGS_FILENAME,
)


PORTFOLIO_FIXTURE = ROOT / "tests" / "fixtures" / "portfolio_risk_cockpit" / "sample_portfolio_v050.csv"
SHORT_PUT_FIXTURE = ROOT / "tests" / "fixtures" / "short_put_risk_monitor" / "sample_short_puts_v051.csv"
MARKET_FIXTURE = ROOT / "tests" / "fixtures" / "risk_cockpit_pipeline" / "fixture_market_data_v052.csv"
SCRIPT = ROOT / "scripts" / "risk_cockpit_pipeline.py"

EXPECTED_INDEX_KEYS = {
    "boundary",
    "enrichment_status",
    "files_created",
    "generated_at",
    "market_data_fixture_path",
    "market_data_status",
    "output_dir",
    "portfolio_input_path",
    "portfolio_report_dir",
    "portfolio_status",
    "review_required",
    "run_id",
    "schema_version",
    "short_put_input_path",
    "short_put_report_dir",
    "short_put_status",
    "warning_codes",
}

EXPECTED_FAILURE_INDEX_KEYS = EXPECTED_INDEX_KEYS | {"error_message"}

REQUIRED_OUTPUTS = {
    REPORT_FILENAME,
    INDEX_FILENAME,
    ARTIFACT_SUMMARY_FILENAME,
    WARNING_SUMMARY_FILENAME,
    MARKET_DATA_SNAPSHOT_FILENAME,
    ENRICHMENT_SUMMARY_FILENAME,
    WARNINGS_FILENAME,
}


def test_pipeline_can_run_foundation_reports_from_fixture_inputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "reports" / "risk_cockpit_pipeline" / "v052" / "20260613"
        result = run_pipeline(
            portfolio_input=PORTFOLIO_FIXTURE,
            short_put_input=SHORT_PUT_FIXTURE,
            market_data_fixture=MARKET_FIXTURE,
            out_dir=out_dir,
            run_foundation_reports=True,
            as_of_date="2026-06-13",
        )

        assert REQUIRED_OUTPUTS.issubset({path.name for path in out_dir.iterdir()})
        assert (out_dir / "portfolio_risk_cockpit" / "portfolio_risk_summary.json").exists()
        assert (out_dir / "short_put_risk_monitor" / "short_put_risk_summary.json").exists()
        assert result.index["boundary"]["live_market_data"] is False
        assert result.index["boundary"]["fixture_market_data_only"] is True


def test_pipeline_can_read_existing_report_artifact_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first_out = root / "reports" / "risk_cockpit_pipeline" / "v052" / "first"
        first = run_pipeline(
            portfolio_input=PORTFOLIO_FIXTURE,
            short_put_input=SHORT_PUT_FIXTURE,
            market_data_fixture=MARKET_FIXTURE,
            out_dir=first_out,
            run_foundation_reports=True,
            as_of_date="2026-06-13",
        )
        second_out = root / "reports" / "risk_cockpit_pipeline" / "v052" / "second"
        second = run_pipeline(
            portfolio_report_dir=first.portfolio_report_dir,
            short_put_report_dir=first.short_put_report_dir,
            market_data_fixture=MARKET_FIXTURE,
            out_dir=second_out,
            as_of_date="2026-06-13",
        )

        assert second.portfolio_input_path == ""
        assert second.short_put_input_path == ""
        assert (second_out / INDEX_FILENAME).exists()


def test_market_fixture_row_must_be_explicitly_fixture_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_market_fixture(Path(tmp), fixture_only="false")

        with pytest.raises(RiskCockpitPipelineError) as exc_info:
            load_fixture_market_data(path)

    message = str(exc_info.value)
    assert "MARKET_DATA_NOT_FIXTURE" in message
    provider = FixtureMarketDataProvider()
    assert provider.provider_level == "Level 0"
    assert provider.network_access is False
    assert provider.live_market_data is False
    assert provider.fixture_only is True


def test_market_fixture_failure_writes_fail_closed_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_market = _write_market_fixture(root, fixture_only="false")
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "market_failed"

        with pytest.raises(RiskCockpitPipelineFailure) as exc_info:
            run_pipeline(
                portfolio_input=PORTFOLIO_FIXTURE,
                short_put_input=SHORT_PUT_FIXTURE,
                market_data_fixture=bad_market,
                out_dir=out_dir,
                run_foundation_reports=True,
                as_of_date="2026-06-13",
            )
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert exc_info.value.index_path == str(out_dir / INDEX_FILENAME)
        assert set(index) == EXPECTED_FAILURE_INDEX_KEYS
        assert "PIPELINE_FAILED_CLOSED" in index["warning_codes"]
        assert "MARKET_DATA_LOAD_FAILED" in index["warning_codes"]
        assert "MARKET_DATA_NOT_FIXTURE" in index["error_message"]
        assert index["market_data_status"] == "failed"
        assert index["review_required"] is True
        assert index["boundary"]["risk_report_only"] is True
        assert index["boundary"]["broker_connection"] is False
        assert index["boundary"]["ibkr_content_inspected"] is False
        assert index["boundary"]["live_market_data"] is False
        assert index["boundary"]["market_data_provider_level"] == "Level 0"
        assert index["boundary"]["fixture_market_data_only"] is True
        assert index["boundary"]["recommendation_output"] is False


def test_malformed_portfolio_json_writes_artifact_failure_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first_out = _run_fixture_pipeline(root)
        portfolio_summary = first_out / "portfolio_risk_cockpit" / "portfolio_risk_summary.json"
        portfolio_summary.write_text("{not json", encoding="utf-8")
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "artifact_failed"

        with pytest.raises(RiskCockpitPipelineFailure):
            run_pipeline(
                portfolio_report_dir=first_out / "portfolio_risk_cockpit",
                short_put_report_dir=first_out / "short_put_risk_monitor",
                market_data_fixture=MARKET_FIXTURE,
                out_dir=out_dir,
                as_of_date="2026-06-13",
            )
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert "PIPELINE_FAILED_CLOSED" in index["warning_codes"]
        assert "ARTIFACT_READ_FAILED" in index["warning_codes"]
        assert index["portfolio_status"] == "failed"
        assert "error_message" in index


def test_foundation_report_failure_writes_failure_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "foundation_failed"

        with pytest.raises(RiskCockpitPipelineFailure):
            run_pipeline(
                portfolio_input=root / "safe_missing_fixture.csv",
                short_put_input=SHORT_PUT_FIXTURE,
                market_data_fixture=MARKET_FIXTURE,
                out_dir=out_dir,
                run_foundation_reports=True,
                as_of_date="2026-06-13",
            )
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert "PIPELINE_FAILED_CLOSED" in index["warning_codes"]
        assert "FOUNDATION_REPORT_FAILED" in index["warning_codes"]
        assert index["portfolio_status"] == "failed"
        assert index["boundary"]["trading"] is False


def test_pipeline_index_json_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert set(index) == EXPECTED_INDEX_KEYS
        assert index["schema_version"] == "v0.5.2-phase1"
        assert index["boundary"]["risk_report_only"] is True
        assert index["boundary"]["investment_recommendation"] is False
        assert index["boundary"]["options_recommendation"] is False
        assert index["boundary"]["broker_connection"] is False
        assert index["boundary"]["ibkr_content_inspected"] is False
        assert index["boundary"]["trading"] is False
        assert index["boundary"]["order_placement"] is False
        assert index["boundary"]["market_data_provider_level"] == "Level 0"
        assert index["boundary"]["recommendation_output"] is False
        assert set(index["files_created"]) == {str(out_dir / filename) for filename in REQUIRED_OUTPUTS}


def test_artifact_summary_csv_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))

        assert _fieldnames(out_dir / ARTIFACT_SUMMARY_FILENAME) == ARTIFACT_SUMMARY_FIELDS


def test_warning_summary_csv_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))

        assert _fieldnames(out_dir / WARNING_SUMMARY_FILENAME) == WARNING_SUMMARY_FIELDS


def test_market_data_snapshot_csv_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))

        assert _fieldnames(out_dir / MARKET_DATA_SNAPSHOT_FILENAME) == MARKET_DATA_SNAPSHOT_FIELDS


def test_enrichment_summary_csv_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))

        assert _fieldnames(out_dir / ENRICHMENT_SUMMARY_FILENAME) == ENRICHMENT_SUMMARY_FIELDS


def test_missing_portfolio_artifact_emits_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first_out = _run_fixture_pipeline(root)
        portfolio_summary = first_out / "portfolio_risk_cockpit" / "portfolio_risk_summary.json"
        portfolio_summary.unlink()
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "missing_portfolio"
        run_pipeline(
            portfolio_report_dir=first_out / "portfolio_risk_cockpit",
            short_put_report_dir=first_out / "short_put_risk_monitor",
            market_data_fixture=MARKET_FIXTURE,
            out_dir=out_dir,
            as_of_date="2026-06-13",
        )
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert "MISSING_PORTFOLIO_ARTIFACT" in index["warning_codes"]


def test_missing_short_put_artifact_emits_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first_out = _run_fixture_pipeline(root)
        short_summary = first_out / "short_put_risk_monitor" / "short_put_risk_summary.json"
        short_summary.unlink()
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "missing_short_put"
        run_pipeline(
            portfolio_report_dir=first_out / "portfolio_risk_cockpit",
            short_put_report_dir=first_out / "short_put_risk_monitor",
            market_data_fixture=MARKET_FIXTURE,
            out_dir=out_dir,
            as_of_date="2026-06-13",
        )
        index = json.loads((out_dir / INDEX_FILENAME).read_text(encoding="utf-8"))

        assert "MISSING_SHORT_PUT_ARTIFACT" in index["warning_codes"]


def test_missing_market_data_emits_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))
        rows = _rows(out_dir / ENRICHMENT_SUMMARY_FILENAME)

        assert any("MISSING_MARKET_DATA" in row["warning_codes"] for row in rows)


def test_stale_market_data_emits_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))
        rows = _rows(out_dir / ENRICHMENT_SUMMARY_FILENAME)

        assert any(row["ticker"] == "MSFT" and "STALE_MARKET_DATA" in row["warning_codes"] for row in rows)


def test_short_put_price_mismatch_emits_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_fixture_pipeline(Path(tmp))
        rows = _rows(out_dir / ENRICHMENT_SUMMARY_FILENAME)

        assert any(
            row["ticker"] == "AVGO"
            and row["source_context"] == "short_put_position"
            and "PRICE_MISMATCH_NEEDS_REVIEW" in row["warning_codes"]
            for row in rows
        )


def test_real_data_looking_paths_fail_closed_before_reads() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = [
            root / "portfolio.csv",
            root / "IBKR Positions" / "positions.csv",
            root / "ibkr_export.csv",
            root / "broker_export.csv",
            root / "client_export.csv",
        ]

        for path in paths:
            with pytest.raises(RiskCockpitPipelineError) as exc_info:
                assert_safe_input_path(path)
            message = str(exc_info.value)
            assert "DISALLOWED_REAL_DATA_PATH" in message
            assert "not found" not in message


def test_no_network_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("Risk Cockpit Pipeline must not open network sockets by default")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        result = run_pipeline(
            portfolio_input=PORTFOLIO_FIXTURE,
            short_put_input=SHORT_PUT_FIXTURE,
            market_data_fixture=MARKET_FIXTURE,
            out_dir=Path(tmp) / "reports" / "risk_cockpit_pipeline" / "v052" / "network",
            run_foundation_reports=True,
            as_of_date="2026-06-13",
        )

    assert result.index["boundary"]["live_market_data"] is False


def test_no_forbidden_imports_or_calls() -> None:
    source_files = list((SRC / "ai_pm_agent" / "risk_cockpit_pipeline").glob("*.py")) + [SCRIPT]
    imported_modules = set()
    call_names = set()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    call_names.add(node.func.id)
                if isinstance(node.func, ast.Attribute):
                    call_names.add(node.func.attr)

    forbidden_imports = {
        "ai_pm_agent.evidence_db.http_client",
        "ib_insync",
        "openai",
        "requests",
        "urllib",
        "yfinance",
    }
    assert forbidden_imports.isdisjoint(imported_modules)
    dangerous_call_names = {
        "placeOrder",
        "place_order",
        "submit_order",
        "recommend_trade",
        "recommend",
        "buy",
        "sell",
        "roll",
        "close_position",
        "open_position",
    }
    assert dangerous_call_names.isdisjoint(call_names)
    forbidden_markers = [
        "OpenRouter",
        "DeepSeek",
        "build_pm_prompt",
        "run_company_research",
        "placeOrder",
        "place_order",
        "submit_order",
    ]
    for marker in forbidden_markers:
        assert marker not in combined


def test_generated_outputs_stay_under_ignored_reports_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert default_output_dir().parts[:3] == ("reports", "risk_cockpit_pipeline", "v052")
    assert "reports/" in gitignore


def test_cli_writes_outputs_and_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "cli"
        ok = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--portfolio-input",
                str(PORTFOLIO_FIXTURE),
                "--short-put-input",
                str(SHORT_PUT_FIXTURE),
                "--market-data-fixture",
                str(MARKET_FIXTURE),
                "--out-dir",
                str(out_dir),
                "--run-foundation-reports",
                "--as-of-date",
                "2026-06-13",
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        failed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--portfolio-report-dir",
                str(root / "portfolio.csv"),
                "--short-put-report-dir",
                str(root / "safe_short_put_reports"),
                "--market-data-fixture",
                str(MARKET_FIXTURE),
                "--out-dir",
                str(root / "bad"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert ok.returncode == 0
        assert (out_dir / REPORT_FILENAME).exists()
        assert "Risk Cockpit Pipeline wrote" in ok.stdout
        assert failed.returncode == 2
        assert "failed closed" in failed.stderr
        assert "DISALLOWED_REAL_DATA_PATH" in failed.stderr


def test_cli_post_start_failure_prints_failure_index_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_market = _write_market_fixture(root, fixture_only="false")
        out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "cli_failed"

        failed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--portfolio-input",
                str(PORTFOLIO_FIXTURE),
                "--short-put-input",
                str(SHORT_PUT_FIXTURE),
                "--market-data-fixture",
                str(bad_market),
                "--out-dir",
                str(out_dir),
                "--run-foundation-reports",
                "--as-of-date",
                "2026-06-13",
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert failed.returncode == 2
        assert "Risk Cockpit Pipeline failed closed" in failed.stderr
        assert str(out_dir / INDEX_FILENAME) in failed.stderr
        assert (out_dir / INDEX_FILENAME).exists()


def _run_fixture_pipeline(root: Path) -> Path:
    out_dir = root / "reports" / "risk_cockpit_pipeline" / "v052" / "20260613"
    run_pipeline(
        portfolio_input=PORTFOLIO_FIXTURE,
        short_put_input=SHORT_PUT_FIXTURE,
        market_data_fixture=MARKET_FIXTURE,
        out_dir=out_dir,
        run_foundation_reports=True,
        as_of_date="2026-06-13",
    )
    return out_dir


def _fieldnames(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle).fieldnames or [])


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_market_fixture(tmp_path: Path, *, fixture_only: str) -> Path:
    path = tmp_path / "safe_market_data_fixture.csv"
    row = {
        "ticker": "NVDA",
        "price": "126",
        "currency": "USD",
        "as_of_date": "2026-06-13",
        "source": "local_fixture",
        "source_confidence": "medium",
        "fixture_only": fixture_only,
        "notes": "test fixture",
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return path

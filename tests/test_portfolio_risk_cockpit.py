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

from ai_pm_agent.portfolio_risk_cockpit.exposure import calculate_exposure_by_ticker
from ai_pm_agent.portfolio_risk_cockpit.loader import PortfolioRiskCockpitError, load_positions_from_csv
from ai_pm_agent.portfolio_risk_cockpit.report_writer import default_output_dir
from ai_pm_agent.portfolio_risk_cockpit.runner import run_cockpit
from ai_pm_agent.portfolio_risk_cockpit.schema import (
    CURRENCY_EXPOSURE_FILENAME,
    REPORT_FILENAME,
    STRESS_SCENARIOS_FILENAME,
    SUMMARY_FILENAME,
    THEME_EXPOSURE_FILENAME,
    TICKER_EXPOSURE_FILENAME,
    WARNINGS_FILENAME,
)


FIXTURE = ROOT / "tests" / "fixtures" / "portfolio_risk_cockpit" / "sample_portfolio_v050.csv"
SCRIPT = ROOT / "scripts" / "portfolio_risk_cockpit.py"


EXPECTED_SUMMARY_KEYS = {
    "as_of_date",
    "boundary",
    "concentration_top5",
    "counts",
    "exposure_by_region",
    "input_path",
    "schema_version",
    "totals",
    "warning_codes",
}


def test_fixture_portfolio_loads_successfully() -> None:
    positions = load_positions_from_csv(FIXTURE)

    assert len(positions) == 7
    assert positions[0].ticker == "TQQQ"
    assert positions[0].currency == "USD"


def test_missing_required_fields_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        path = _write_rows(tmp_path, [{"ticker": "", "currency": "USD"}])

        with pytest.raises(PortfolioRiskCockpitError, match="ticker must not be blank"):
            load_positions_from_csv(path)

        missing_currency = _write_rows(tmp_path, [{"ticker": "NVDA", "currency": ""}], name="missing_currency.csv")
        with pytest.raises(PortfolioRiskCockpitError, match="currency must not be blank"):
            load_positions_from_csv(missing_currency)


def test_invalid_numeric_values_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_rows(Path(tmp), [{"ticker": "NVDA", "currency": "USD", "market_value": "not-a-number"}])

        with pytest.raises(PortfolioRiskCockpitError, match="invalid numeric value for market_value"):
            load_positions_from_csv(path)


def test_leveraged_etf_exposure_multiplier_is_applied() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cockpit(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")
        tqqq = next(row for row in result.exposure_by_ticker if row["ticker"] == "TQQQ")

        assert tqqq["gross_market_value"] == 10000.0
        assert tqqq["leverage_adjusted_exposure"] == 30000.0


def test_leveraged_etf_requires_explicit_multiplier() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_rows(
            Path(tmp),
            [
                {
                    "ticker": "TQQQ",
                    "instrument_type": "leveraged_etf",
                    "currency": "USD",
                    "exposure_multiplier": "",
                }
            ],
        )

        with pytest.raises(PortfolioRiskCockpitError, match="leveraged ETF must explicitly show exposure_multiplier"):
            load_positions_from_csv(path)


def test_short_option_rows_are_needs_review() -> None:
    positions = load_positions_from_csv(FIXTURE)
    short_option = next(position for position in positions if position.ticker == "NVDA_PUT_SHORT")

    assert short_option.review_status == "NEEDS_REVIEW"
    assert "SHORT_OPTION_NEEDS_REVIEW" in short_option.warning_codes


def test_stress_scenario_outputs_are_generated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_cockpit(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_SCENARIOS_FILENAME).open(newline="", encoding="utf-8")))

        assert [row["scenario"] for row in rows] == ["Nasdaq -10%", "Semis -15%", "USD/SGD -5%", "ETH/BTC -20%"]
        assert any(row["impacted_exposure"] != "0" for row in rows)


def test_report_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = run_cockpit(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        summary = json.loads((tmp_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))

        assert set(summary) == EXPECTED_SUMMARY_KEYS
        assert summary["schema_version"] == "v0.5.0-phase1"
        assert summary["boundary"]["risk_report_only"] is True
        assert summary["boundary"]["investment_recommendation"] is False
        assert (tmp_path / REPORT_FILENAME).exists()
        assert (tmp_path / TICKER_EXPOSURE_FILENAME).exists()
        assert (tmp_path / THEME_EXPOSURE_FILENAME).exists()
        assert (tmp_path / CURRENCY_EXPOSURE_FILENAME).exists()
        assert (tmp_path / WARNINGS_FILENAME).exists()
        assert "This is a risk report, not an investment recommendation." in (
            tmp_path / REPORT_FILENAME
        ).read_text(encoding="utf-8")
        assert result.files["summary"].endswith(SUMMARY_FILENAME)


def test_unknown_instrument_type_becomes_needs_review() -> None:
    positions = load_positions_from_csv(FIXTURE)
    unknown = next(position for position in positions if position.ticker == "ALT_UNKNOWN")

    assert unknown.review_status == "NEEDS_REVIEW"
    assert "UNKNOWN_INSTRUMENT_TYPE" in unknown.warning_codes


def test_no_forbidden_imports_or_calls() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "__init__.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "models.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "schema.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "loader.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "exposure.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "stress.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "report_writer.py",
        SRC / "ai_pm_agent" / "portfolio_risk_cockpit" / "runner.py",
        SCRIPT,
    ]
    imported_modules = set()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_imports = {
        "ai_pm_agent.portfolio.ibkr_import",
        "ai_pm_agent.portfolio.runner",
        "ai_pm_agent.company_db",
        "ai_pm_agent.evidence_db.http_client",
        "ib_insync",
        "openai",
        "requests",
        "yfinance",
    }
    assert forbidden_imports.isdisjoint(imported_modules)
    forbidden_call_markers = [
        "OpenRouter",
        "DeepSeek",
        "build_pm_prompt",
        "run_company_research",
        "placeOrder",
        "place_order",
        "submit_order",
    ]
    for marker in forbidden_call_markers:
        assert marker not in combined


def test_no_network_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("Portfolio Risk Cockpit must not open network sockets by default")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cockpit(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")

    assert result.summary["boundary"]["network_access"] is False


def test_generated_outputs_stay_under_ignored_reports_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert default_output_dir().parts[:3] == ("reports", "portfolio_risk_cockpit", "v050")
    assert "reports/" in gitignore


def test_cli_writes_outputs_and_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_dir = tmp_path / "out"
        ok = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(FIXTURE),
                "--out-dir",
                str(out_dir),
                "--as-of-date",
                "2026-06-13",
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        bad_input = _write_rows(tmp_path, [{"ticker": "", "currency": "USD"}], name="bad_cli.csv")
        failed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(bad_input), "--out-dir", str(tmp_path / "bad")],
            check=False,
            capture_output=True,
            text=True,
        )

        assert ok.returncode == 0
        assert (out_dir / REPORT_FILENAME).exists()
        assert failed.returncode == 2
        assert "failed closed" in failed.stderr


def test_calculate_exposure_by_ticker_is_deterministic() -> None:
    rows = calculate_exposure_by_ticker(load_positions_from_csv(FIXTURE))

    assert [row["ticker"] for row in rows[:3]] == ["TQQQ", "NVDA_PUT_SHORT", "NVDA"]


def _write_rows(tmp_path: Path, overrides: list[dict[str, str]], *, name: str = "input.csv") -> Path:
    default = {
        "ticker": "NVDA",
        "instrument_type": "stock",
        "quantity": "1",
        "currency": "USD",
        "market_value": "100",
        "notional_value": "100",
        "exposure_multiplier": "1",
        "underlying_ticker": "",
        "theme": "AI infrastructure",
        "region": "North America",
        "notes": "test row",
    }
    rows = [{**default, **override} for override in overrides]
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(default))
        writer.writeheader()
        writer.writerows(rows)
    return path

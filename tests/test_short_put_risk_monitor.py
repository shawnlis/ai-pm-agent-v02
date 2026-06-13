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

from ai_pm_agent.short_put_risk_monitor.loader import ShortPutRiskMonitorError, load_short_puts_from_csv
from ai_pm_agent.short_put_risk_monitor.report_writer import default_output_dir
from ai_pm_agent.short_put_risk_monitor.runner import run_monitor
from ai_pm_agent.short_put_risk_monitor.schema import (
    POSITIONS_FILENAME,
    REPORT_FILENAME,
    SHORT_PUT_STRESS_FIELDS,
    STRESS_FILENAME,
    SUMMARY_FILENAME,
    WARNINGS_FILENAME,
)


FIXTURE = ROOT / "tests" / "fixtures" / "short_put_risk_monitor" / "sample_short_puts_v051.csv"
SCRIPT = ROOT / "scripts" / "short_put_risk_monitor.py"

EXPECTED_SUMMARY_KEYS = {
    "as_of_date",
    "boundary",
    "counts",
    "input_path",
    "schema_version",
    "totals",
    "warning_codes",
}


def test_fixture_short_puts_load_successfully() -> None:
    positions = load_short_puts_from_csv(FIXTURE)

    assert len(positions) == 6
    assert positions[0].option_id == "NVDA_20260717_100P"
    assert positions[0].underlying_ticker == "NVDA"


def test_missing_required_fields_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_rows(Path(tmp), [{"option_id": ""}])

        with pytest.raises(ShortPutRiskMonitorError, match="option_id must not be blank"):
            load_short_puts_from_csv(path)


def test_portfolio_csv_path_fails_closed_before_reading() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "portfolio.csv"

        with pytest.raises(ShortPutRiskMonitorError) as exc_info:
            load_short_puts_from_csv(path)

    message = str(exc_info.value)
    assert "DISALLOWED_REAL_SHORT_PUT_INPUT" in message
    assert "fixture CSV input only" in message
    assert "not found" not in message


def test_ibkr_positions_path_fails_closed_before_reading() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "IBKR Positions" / "short_puts.csv"

        with pytest.raises(ShortPutRiskMonitorError) as exc_info:
            load_short_puts_from_csv(path)

    message = str(exc_info.value)
    assert "DISALLOWED_REAL_SHORT_PUT_INPUT" in message
    assert "fixture CSV input only" in message
    assert "not found" not in message


def test_ibkr_broker_or_client_path_text_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        disallowed_paths = [
            root / "ibkr_short_puts.csv",
            root / "broker_short_puts.csv",
            root / "client_short_puts.csv",
        ]

        for path in disallowed_paths:
            with pytest.raises(ShortPutRiskMonitorError) as exc_info:
                load_short_puts_from_csv(path)
            message = str(exc_info.value)
            assert "DISALLOWED_REAL_SHORT_PUT_INPUT" in message
            assert "not found" not in message


def test_invalid_numeric_values_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_rows(Path(tmp), [{"strike": "not-a-number"}])

        with pytest.raises(ShortPutRiskMonitorError, match="invalid numeric value for strike"):
            load_short_puts_from_csv(path)


def test_expired_option_gets_expired_option_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_monitor(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")
        expired = _position_row(result, "MU_20260601_120P")

    assert expired["review_status"] == "NEEDS_REVIEW"
    assert "EXPIRED_OPTION" in expired["warning_codes"]


def test_below_strike_option_gets_below_strike_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_monitor(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")
        row = _position_row(result, "MU_20260601_120P")

    assert "BELOW_STRIKE" in row["warning_codes"]


def test_below_breakeven_option_gets_below_breakeven_warning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_monitor(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")
        row = _position_row(result, "AVGO_20260717_900P")

    assert "BELOW_BREAKEVEN" in row["warning_codes"]


def test_stress_scenario_outputs_are_generated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8")))

    assert len(rows) == 30
    assert {row["scenario"] for row in rows} == {
        "underlying -10%",
        "underlying -20%",
        "underlying -30%",
        "underlying to strike",
        "underlying to breakeven",
    }
    assert rows[0].keys() == set(SHORT_PUT_STRESS_FIELDS)


def test_stress_downside_is_never_negative() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8")))

    assert all(float(row["max_simple_downside_at_stress"]) >= 0 for row in rows)


def test_stress_positive_pnl_still_has_zero_downside() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8")))
        row = next(
            item
            for item in rows
            if item["option_id"] == "NVDA_20260717_100P" and item["scenario"] == "underlying -10%"
        )

    assert float(row["max_simple_downside_at_stress"]) == 0.0
    assert float(row["estimated_pnl_at_stress"]) > 0


def test_stress_negative_pnl_has_positive_downside() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8")))
        row = next(
            item
            for item in rows
            if item["option_id"] == "AVGO_20260717_900P" and item["scenario"] == "underlying -20%"
        )

    assert float(row["max_simple_downside_at_stress"]) > 0
    assert float(row["estimated_pnl_at_stress"]) < 0


def test_stress_csv_schema_includes_estimated_pnl() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        with (tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []

    assert fieldnames == SHORT_PUT_STRESS_FIELDS
    assert "estimated_pnl_at_stress" in fieldnames


def test_stress_rows_inherit_position_warning_codes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        rows = list(csv.DictReader((tmp_path / STRESS_FILENAME).open(newline="", encoding="utf-8")))
        mu_row = next(
            row
            for row in rows
            if row["option_id"] == "MU_20260601_120P" and row["scenario"] == "underlying -10%"
        )

    assert mu_row["review_status"] == "NEEDS_REVIEW"
    assert "EXPIRED_OPTION" in mu_row["warning_codes"]
    assert "BELOW_STRIKE" in mu_row["warning_codes"]


def test_report_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = run_monitor(input_path=FIXTURE, out_dir=tmp_path, as_of_date="2026-06-13")
        summary = json.loads((tmp_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))

        assert set(summary) == EXPECTED_SUMMARY_KEYS
        assert summary["schema_version"] == "v0.5.1-phase1"
        assert summary["boundary"]["fixture_input_only"] is True
        assert summary["boundary"]["options_recommendation"] is False
        assert summary["boundary"]["broker_connection"] is False
        assert summary["boundary"]["ibkr_content_inspected"] is False
        assert summary["boundary"]["pm_prompt_wiring"] is False
        assert (tmp_path / REPORT_FILENAME).exists()
        assert (tmp_path / POSITIONS_FILENAME).exists()
        assert (tmp_path / STRESS_FILENAME).exists()
        assert (tmp_path / WARNINGS_FILENAME).exists()
        assert "This is a short put risk report, not an options trading recommendation." in (
            tmp_path / REPORT_FILENAME
        ).read_text(encoding="utf-8")
        assert result.files["summary"].endswith(SUMMARY_FILENAME)


def test_no_forbidden_imports_or_calls() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "__init__.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "models.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "schema.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "loader.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "risk_calculator.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "stress.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "report_writer.py",
        SRC / "ai_pm_agent" / "short_put_risk_monitor" / "runner.py",
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
        "recommend_roll",
        "recommend_close",
        "recommend_open",
    ]
    for marker in forbidden_call_markers:
        assert marker not in combined


def test_no_network_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("Short Put Risk Monitor must not open network sockets by default")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        result = run_monitor(input_path=FIXTURE, out_dir=Path(tmp), as_of_date="2026-06-13")

    assert result.summary["boundary"]["network_access"] is False


def test_generated_outputs_stay_under_ignored_reports_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert default_output_dir().parts[:3] == ("reports", "short_put_risk_monitor", "v051")
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
        bad_input = _write_rows(tmp_path, [{"strike": "bad"}], name="bad_cli.csv")
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


def _position_row(result, option_id: str) -> dict[str, object]:
    return next(row for row in result.position_rows if row["option_id"] == option_id)


def _write_rows(tmp_path: Path, overrides: list[dict[str, str]], *, name: str = "input.csv") -> Path:
    default = {
        "option_id": "NVDA_TEST_100P",
        "underlying_ticker": "NVDA",
        "expiry_date": "2026-07-17",
        "strike": "100",
        "contracts": "1",
        "contract_multiplier": "100",
        "premium_collected": "300",
        "current_underlying_price": "120",
        "currency": "USD",
        "underlying_theme": "AI infrastructure",
        "notes": "test row",
    }
    rows = [{**default, **override} for override in overrides]
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(default))
        writer.writeheader()
        writer.writerows(rows)
    return path

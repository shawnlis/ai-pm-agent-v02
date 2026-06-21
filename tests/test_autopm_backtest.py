from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.backtest import AutopmBacktestError, run_backtest_from_fixture, write_backtest_result


FIXTURE = ROOT / "tests" / "fixtures" / "autopm_backtest"


def test_deterministic_backtest_output() -> None:
    first = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json").to_dict()
    second = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json").to_dict()

    assert first == second
    assert first["run_id"] == "fixture-backtest-v01"
    assert first["simulated"] is True
    assert first["not_broker_execution"] is True


def test_missing_prices_fail_closed(tmp_path: Path) -> None:
    spec = json.loads((FIXTURE / "backtest_fixture.json").read_text(encoding="utf-8"))
    spec["prices_file"] = "missing_prices.json"
    path = tmp_path / "backtest_fixture.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    with pytest.raises((AutopmBacktestError, ValueError)):
        run_backtest_from_fixture(path)


def test_no_lookahead_fields_rejected(tmp_path: Path) -> None:
    spec = json.loads((FIXTURE / "backtest_fixture.json").read_text(encoding="utf-8"))
    spec["rebalance_events"][0]["proposal"]["proposed_trades"][0]["source_date"] = "2026-03-15"
    (tmp_path / "initial_state.json").write_text((FIXTURE / "initial_state.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prices.json").write_text((FIXTURE / "prices.json").read_text(encoding="utf-8"), encoding="utf-8")
    path = tmp_path / "backtest_fixture.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    with pytest.raises(AutopmBacktestError, match="lookahead"):
        run_backtest_from_fixture(path)


def test_turnover_max_drawdown_and_hit_rate_calculated() -> None:
    result = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json")

    assert result.turnover > 0
    assert result.max_drawdown > 0
    assert result.hit_rate == 0.5
    assert result.realized_pnl == 0
    assert result.unrealized_pnl > 0


def test_benchmark_comparison_works() -> None:
    result = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json")

    assert result.benchmark_return == pytest.approx(0.06)


def test_backtest_exposure_and_outcome_summary() -> None:
    result = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json")

    assert "AI hardware" in result.exposure_by_theme
    assert "Asia" in result.exposure_by_region
    assert result.recommendation_outcome_summary == {"count": 2, "hit_count": 1, "miss_count": 1}


def test_write_backtest_result_uses_explicit_tempdir(tmp_path: Path) -> None:
    result = run_backtest_from_fixture(FIXTURE / "backtest_fixture.json")
    out = tmp_path / "backtest_result.json"

    write_backtest_result(result, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["run_id"] == "fixture-backtest-v01"


def test_broker_client_account_paths_rejected(tmp_path: Path) -> None:
    risky = tmp_path / "broker_account_backtest.json"
    risky.write_text('{"fixture_only": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="refusing"):
        run_backtest_from_fixture(risky)


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert run_backtest_from_fixture(FIXTURE / "backtest_fixture.json").run_id == "fixture-backtest-v01"


def test_no_broker_execution_imports() -> None:
    for path in [SRC / "ai_pm_agent" / "autopm" / "backtest.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")):
                assert "broker" not in stripped
                assert "ibkr" not in stripped
                assert "execution" not in stripped

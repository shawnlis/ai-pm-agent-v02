from __future__ import annotations

from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.state_store import AutopmStateStoreError, load_monitor_state, read_fixture_table_or_json


FIXTURE = ROOT / "tests" / "fixtures" / "autopm_monitor"


def test_loads_explicit_prior_and_current_state() -> None:
    prior = load_monitor_state(FIXTURE / "prior")
    current = load_monitor_state(FIXTURE / "current")

    assert prior.run_id == "prior-run"
    assert current.run_id == "current-run"
    assert current.source_manifest_hash == "src-current"
    assert current.recommendations
    assert current.rebalance_rows


def test_rejects_broker_client_account_ibkr_paths(tmp_path: Path) -> None:
    risky = tmp_path / "IBKR_account_state.json"
    risky.write_text("{}", encoding="utf-8")

    with pytest.raises(AutopmStateStoreError, match="refusing"):
        load_monitor_state(risky)


def test_supports_json_and_csv_fixture_inputs(tmp_path: Path) -> None:
    csv_path = tmp_path / "rankings.csv"
    csv_path.write_text("ticker,rank,tier\nABC,1,top_pick\n", encoding="utf-8")

    rows = read_fixture_table_or_json(csv_path)

    assert rows == [{"ticker": "ABC", "rank": "1", "tier": "top_pick"}]


def test_no_implicit_scan_of_reports_or_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "explicit_run"
    run_dir.mkdir()
    (run_dir / "autopm_run_manifest.json").write_text('{"run_id": "explicit"}', encoding="utf-8")
    nested = run_dir / "reports"
    nested.mkdir()
    (nested / "autopm_rankings.json").write_text('{"rankings": [{"ticker": "SHOULD_NOT_LOAD"}]}', encoding="utf-8")

    state = load_monitor_state(run_dir)

    assert state.run_id == "explicit"
    assert state.rankings == ()


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert load_monitor_state(FIXTURE / "prior").run_id == "prior-run"


def test_no_broker_execution_imports() -> None:
    text = (SRC / "ai_pm_agent" / "autopm" / "state_store.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("import ", "from ")):
            assert "broker" not in stripped
            assert "ibkr" not in stripped
            assert "execution" not in stripped

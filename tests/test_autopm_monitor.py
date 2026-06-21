from __future__ import annotations

import csv
import json
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.monitor import compare_states, monitor_explicit_paths, write_monitor_artifacts
from ai_pm_agent.autopm.state_store import load_monitor_state


FIXTURE = ROOT / "tests" / "fixtures" / "autopm_monitor"


def _alerts() -> dict[str, list]:
    result = compare_states(load_monitor_state(FIXTURE / "prior"), load_monitor_state(FIXTURE / "current"))
    grouped: dict[str, list] = {}
    for alert in result.alerts:
        grouped.setdefault(alert.alert_type, []).append(alert)
    return grouped


def test_prior_current_diff_detects_new_and_removed_top_pick() -> None:
    alerts = _alerts()

    assert alerts["NEW_TOP_PICK"][0].ticker == "NEWTOP"
    assert alerts["REMOVED_TOP_PICK"][0].ticker == "OLDTOP"


def test_rank_upgrade_and_downgrade_detected() -> None:
    alerts = _alerts()

    assert alerts["RANK_UPGRADE"][0].ticker == "UP"
    assert alerts["RANK_DOWNGRADE"][0].ticker == "DOWN"


def test_action_upgrade_and_downgrade_detected() -> None:
    alerts = _alerts()

    assert alerts["ACTION_UPGRADE"][0].ticker == "ACTUP"
    assert alerts["ACTION_DOWNGRADE"][0].ticker == "ACTDOWN"


def test_target_weight_increase_and_decrease_detected() -> None:
    alerts = _alerts()

    assert {alert.ticker for alert in alerts["TARGET_WEIGHT_INCREASE"]} == {"ACTUP", "WTUP"}
    assert {alert.ticker for alert in alerts["TARGET_WEIGHT_DECREASE"]} == {"ACTDOWN", "WTDOWN"}


def test_thesis_kill_stale_evidence_claim_and_validation_alerts() -> None:
    alerts = _alerts()

    assert alerts["THESIS_KILL_TRIGGER_ACTIVE"][0].severity == "critical"
    assert alerts["PRICE_OR_VALUATION_STALE"][0].ticker == "STALE"
    assert alerts["EVIDENCE_STALE"][0].ticker == "EVID"
    assert alerts["CLAIM_AUDIT_FAILED"][0].severity == "critical"
    assert alerts["OUTPUT_VALIDATION_INVALID"][0].severity == "critical"


def test_required_evidence_policy_concentration_cash_alerts() -> None:
    alerts = _alerts()

    assert alerts["REQUIRED_EVIDENCE_MISSING"][0].ticker == "ACTUP"
    assert alerts["POLICY_BREACH"][0].ticker == "POLICY"
    assert alerts["CONCENTRATION_BREACH"][0].ticker == "POLICY"
    assert alerts["CASH_CONSTRAINT"][0].ticker == "POLICY"


def test_paper_drawdown_and_turnover_alerts() -> None:
    alerts = _alerts()

    assert alerts["PAPER_DRAWDOWN_ALERT"][0].severity == "warning"
    assert alerts["TURNOVER_ALERT"][0].severity == "warning"


def test_alert_rows_are_review_triggers_not_trade_instructions() -> None:
    result = compare_states(load_monitor_state(FIXTURE / "prior"), load_monitor_state(FIXTURE / "current"))

    assert result.alerts
    for alert in result.alerts:
        assert alert.manual_review_required is True
        assert alert.not_investment_advice is True
        assert alert.required_next_action == "manual_review"
        assert alert.required_next_action not in {"sell", "trim", "order"}


def test_generated_alert_files_written_only_to_tempdir(tmp_path: Path) -> None:
    result = monitor_explicit_paths(FIXTURE / "prior", FIXTURE / "current", out_dir=tmp_path)

    assert result.alerts
    assert (tmp_path / "AUTOPM_MONITOR_ALERTS.md").exists()
    assert (tmp_path / "autopm_alerts.csv").exists()
    assert (tmp_path / "autopm_monitor_state.json").exists()
    assert (tmp_path / "autopm_monitor_warnings.md").exists()
    rows = list(csv.DictReader((tmp_path / "autopm_alerts.csv").open("r", encoding="utf-8")))
    assert rows
    assert all(row["required_next_action"] == "manual_review" for row in rows)
    state = json.loads((tmp_path / "autopm_monitor_state.json").read_text(encoding="utf-8"))
    assert state["review_triggers_only"] is True


def test_alert_ordering_is_deterministic() -> None:
    first = [alert.to_dict() for alert in compare_states(load_monitor_state(FIXTURE / "prior"), load_monitor_state(FIXTURE / "current")).alerts]
    second = [alert.to_dict() for alert in compare_states(load_monitor_state(FIXTURE / "prior"), load_monitor_state(FIXTURE / "current")).alerts]

    assert first == second


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert compare_states(load_monitor_state(FIXTURE / "prior"), load_monitor_state(FIXTURE / "current")).alerts


def test_no_broker_execution_scheduler_notification_imports() -> None:
    offenders: list[str] = []
    for path in [SRC / "ai_pm_agent" / "autopm" / "monitor.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in ("broker", "ibkr", "execution", "schedule", "telegram", "slack", "email", "whatsapp", "yfinance")):
                offenders.append(f"{path}:{line}")

    assert offenders == []

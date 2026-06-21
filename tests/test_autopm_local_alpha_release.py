from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.backtest import AutopmBacktestError, run_backtest_from_fixture
from ai_pm_agent.autopm.monitor import monitor_explicit_paths
from ai_pm_agent.autopm.paper_portfolio import PaperPortfolioError, apply_rebalance_proposal, load_fixture_prices, load_paper_state
from ai_pm_agent.autopm.state_store import AutopmStateStoreError, load_monitor_state
from ai_pm_agent.cli.autopm import main


SCRIPT = ROOT / "scripts" / "autopm.py"
CLI_FIXTURE = ROOT / "tests" / "fixtures" / "autopm_cli"
SOURCE_PACK = CLI_FIXTURE / "source_pack"
PORTFOLIO = CLI_FIXTURE / "sample_autopm_fixture.csv"
BACKTEST_FIXTURE = ROOT / "tests" / "fixtures" / "autopm_backtest"
PAPER_FIXTURE = ROOT / "tests" / "fixtures" / "autopm_paper_portfolio"
MONITOR_FIXTURE = ROOT / "tests" / "fixtures" / "autopm_monitor"


def test_cli_help_and_validate_inputs_smoke() -> None:
    help_result = subprocess.run([sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True)

    assert help_result.returncode == 0
    assert "validate-inputs" in help_result.stdout
    assert main(["validate-inputs", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--portfolio", str(PORTFOLIO)]) == 0


def test_cli_rank_generic_and_asia_write_tempdir_outputs(tmp_path: Path) -> None:
    generic_out = tmp_path / "generic-rank"
    asia_out = tmp_path / "asia-rank"

    assert main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--out-dir", str(generic_out)]) == 0
    assert main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "asia_ai_hardware", "--out-dir", str(asia_out)]) == 0

    generic = json.loads((generic_out / "autopm_rankings.json").read_text(encoding="utf-8"))
    asia = json.loads((asia_out / "autopm_rankings.json").read_text(encoding="utf-8"))
    assert generic["ranking_only"] is True
    assert asia["strategy"] == "asia_ai_hardware"
    assert "action" not in generic["rankings"][0]
    assert "target_weight_pct" not in generic["rankings"][0]


def test_cli_recommend_requires_explicit_mode_and_rejects_live_recommendation(tmp_path: Path) -> None:
    missing_mode = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "recommend",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--out-dir",
            str(tmp_path / "missing-mode"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert missing_mode.returncode != 0
    assert main(["recommend", "--source-pack", str(SOURCE_PACK), "--portfolio", str(PORTFOLIO), "--mode", "live_recommendation", "--out-dir", str(tmp_path / "live")]) == 2


def test_cli_rebalance_and_output_validator_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / "rebalance"

    assert main(["rebalance", "--source-pack", str(SOURCE_PACK), "--portfolio", str(PORTFOLIO), "--mode", "proposal", "--out-dir", str(out_dir)]) == 0
    proposal = json.loads((out_dir / "autopm_rebalance_proposal.json").read_text(encoding="utf-8"))

    assert proposal["not_executed"] is True
    assert all(row["not_executed"] is True for row in proposal["proposed_trades"])
    assert (out_dir / "AUTOPM_REBALANCE_PROPOSAL.md").exists()
    assert main(["validate-output", "--run-dir", str(out_dir), "--strict"]) == 0
    validation = json.loads((out_dir / "autopm_output_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "VALID"


def test_backtest_rejects_lookahead_fixture(tmp_path: Path) -> None:
    spec = json.loads((BACKTEST_FIXTURE / "backtest_fixture.json").read_text(encoding="utf-8"))
    spec["rebalance_events"][0]["proposal"]["proposed_trades"][0]["source_date"] = "2026-03-15"
    (tmp_path / "initial_state.json").write_text((BACKTEST_FIXTURE / "initial_state.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prices.json").write_text((BACKTEST_FIXTURE / "prices.json").read_text(encoding="utf-8"), encoding="utf-8")
    fixture = tmp_path / "backtest_fixture.json"
    fixture.write_text(json.dumps(spec), encoding="utf-8")

    with pytest.raises(AutopmBacktestError, match="lookahead"):
        run_backtest_from_fixture(fixture)


def test_paper_portfolio_requires_not_executed_true() -> None:
    state = load_paper_state(PAPER_FIXTURE / "initial_state.json")
    prices = load_fixture_prices(PAPER_FIXTURE / "prices.json")
    proposal = json.loads((PAPER_FIXTURE / "proposal.json").read_text(encoding="utf-8"))
    proposal.pop("fixture_only", None)
    proposal["proposed_trades"][0]["not_executed"] = False

    with pytest.raises(PaperPortfolioError, match="not_executed"):
        apply_rebalance_proposal(state, proposal, prices)


def test_monitor_alerts_are_review_triggers_only(tmp_path: Path) -> None:
    result = monitor_explicit_paths(MONITOR_FIXTURE / "prior", MONITOR_FIXTURE / "current", out_dir=tmp_path)

    assert result.alerts
    assert (tmp_path / "AUTOPM_MONITOR_ALERTS.md").exists()
    assert (tmp_path / "autopm_monitor_state.json").exists()
    for alert in result.alerts:
        assert alert.manual_review_required is True
        assert alert.not_investment_advice is True
        assert alert.required_next_action == "manual_review"
        assert alert.required_next_action not in {"sell", "trim", "order"}


def test_broker_client_account_ibkr_paths_are_rejected(tmp_path: Path) -> None:
    risky = tmp_path / "IBKR_client_account_state.json"
    risky.write_text('{"fixture_only": true}', encoding="utf-8")

    with pytest.raises(AutopmStateStoreError, match="refusing"):
        load_monitor_state(risky)
    assert main(["recommend", "--source-pack", str(SOURCE_PACK), "--portfolio", str(tmp_path / "portfolio.csv"), "--mode", "proposal", "--out-dir", str(tmp_path / "blocked")]) == 2


def test_no_network_access_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--out-dir", str(tmp_path / "rank")]) == 0
    assert monitor_explicit_paths(MONITOR_FIXTURE / "prior", MONITOR_FIXTURE / "current").alerts


def test_no_broker_execution_imports_or_tracked_generated_outputs() -> None:
    offenders: list[str] = []
    for path in [
        SRC / "ai_pm_agent" / "cli" / "autopm.py",
        SRC / "ai_pm_agent" / "autopm" / "backtest.py",
        SRC / "ai_pm_agent" / "autopm" / "paper_portfolio.py",
        SRC / "ai_pm_agent" / "autopm" / "monitor.py",
        ROOT / "scripts" / "autopm.py",
    ]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in ("broker", "ibkr", "execution", "yfinance", "openrouter", "deepseek")):
                offenders.append(f"{path}:{line}")

    tracked_outputs = subprocess.run(["git", "ls-files", "reports", "outputs"], cwd=ROOT, check=True, capture_output=True, text=True)
    assert offenders == []
    assert tracked_outputs.stdout.strip() == ""

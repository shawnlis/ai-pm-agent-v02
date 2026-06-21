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

from ai_pm_agent.cli.autopm import main


SCRIPT = ROOT / "scripts" / "autopm.py"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "autopm_cli"
SOURCE_PACK = FIXTURE_ROOT / "source_pack"
PORTFOLIO = FIXTURE_ROOT / "sample_autopm_fixture.csv"


def test_cli_help_works() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "validate-inputs" in result.stdout


def test_validate_inputs_succeeds_on_fixture_inputs() -> None:
    result = main(["validate-inputs", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--portfolio", str(PORTFOLIO)])

    assert result == 0


def test_validate_inputs_fails_closed_on_missing_files(tmp_path: Path) -> None:
    result = main(["validate-inputs", "--source-pack", str(tmp_path / "missing"), "--strategy", "generic"])

    assert result == 2


def test_rank_generic_fixture_creates_ranking_output(tmp_path: Path) -> None:
    out_dir = tmp_path / "rank"

    result = main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--out-dir", str(out_dir)])

    payload = json.loads((out_dir / "autopm_rankings.json").read_text(encoding="utf-8"))
    assert result == 0
    assert payload["ranking_only"] is True
    assert payload["rankings"][0]["ticker"] == "CLIAI"
    assert "action" not in payload["rankings"][0]
    assert "target_weight_pct" not in payload["rankings"][0]


def test_rank_asia_fixture_creates_ranking_output(tmp_path: Path) -> None:
    out_dir = tmp_path / "asia-rank"

    result = main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "asia_ai_hardware", "--out-dir", str(out_dir)])

    payload = json.loads((out_dir / "autopm_rankings.json").read_text(encoding="utf-8"))
    assert result == 0
    assert payload["strategy"] == "asia_ai_hardware"
    assert payload["rankings"][0]["ticker"] == "ASICLI"


def test_recommend_fixture_creates_recommendation_output_and_claim_audit(tmp_path: Path) -> None:
    out_dir = tmp_path / "recommend"

    result = main(
        [
            "recommend",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--mode",
            "proposal",
            "--out-dir",
            str(out_dir),
        ]
    )

    recommendations = json.loads((out_dir / "autopm_recommendations.json").read_text(encoding="utf-8"))
    claim_audit = json.loads((out_dir / "autopm_claim_audit_summary.json").read_text(encoding="utf-8"))
    assert result == 0
    assert recommendations["not_executed"] is True
    assert recommendations["recommendations"][0]["action"] == "buy"
    assert claim_audit["passed"] is True


def test_recommend_without_explicit_mode_fails_closed(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "recommend",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--out-dir",
            str(tmp_path / "recommend"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_recommend_with_real_data_looking_portfolio_path_fails_closed(tmp_path: Path) -> None:
    risky = tmp_path / "portfolio.csv"
    risky.write_text("as_of_date,ticker,quantity,market_value\n2026-06-21,X,1,1\n", encoding="utf-8")

    result = main(
        [
            "recommend",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(risky),
            "--mode",
            "proposal",
            "--out-dir",
            str(tmp_path / "recommend"),
        ]
    )

    assert result == 2


def test_rebalance_fixture_creates_proposal_artifacts_with_not_executed(tmp_path: Path) -> None:
    out_dir = tmp_path / "rebalance"

    result = main(
        [
            "rebalance",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--mode",
            "proposal",
            "--as-of-date",
            "2026-06-21",
            "--out-dir",
            str(out_dir),
        ]
    )

    payload = json.loads((out_dir / "autopm_rebalance_proposal.json").read_text(encoding="utf-8"))
    assert result == 0
    assert payload["not_executed"] is True
    assert all(row["not_executed"] is True for row in payload["proposed_trades"])
    assert (out_dir / "AUTOPM_REBALANCE_PROPOSAL.md").exists()


def test_rebalance_without_explicit_mode_fails_closed(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "rebalance",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--out-dir",
            str(tmp_path / "rebalance"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_validate_output_returns_status_for_fixture_directory(tmp_path: Path) -> None:
    out_dir = tmp_path / "rebalance"
    assert main(["rebalance", "--source-pack", str(SOURCE_PACK), "--portfolio", str(PORTFOLIO), "--mode", "proposal", "--out-dir", str(out_dir)]) == 0

    result = main(["validate-output", "--run-dir", str(out_dir), "--strict"])

    assert result == 0
    validation = json.loads((out_dir / "autopm_output_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "VALID"


def test_live_recommendation_unsupported_in_pr9_execution_path(tmp_path: Path) -> None:
    result = main(
        [
            "recommend",
            "--source-pack",
            str(SOURCE_PACK),
            "--portfolio",
            str(PORTFOLIO),
            "--mode",
            "live_recommendation",
            "--out-dir",
            str(tmp_path / "live"),
        ]
    )

    assert result == 2


def test_no_network_access_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert main(["rank", "--source-pack", str(SOURCE_PACK), "--strategy", "generic", "--out-dir", str(tmp_path / "rank")]) == 0


def test_no_broker_execution_imports() -> None:
    offenders: list[str] = []
    for path in [ROOT / "src" / "ai_pm_agent" / "cli" / "autopm.py", ROOT / "scripts" / "autopm.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in ("broker", "ibkr", "execution", "yfinance")):
                offenders.append(f"{path}:{line}")
    assert offenders == []

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import shutil
import socket
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION
from ai_pm_agent.autopm.output_validator import ValidationStatus, validate_output_dir
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.rebalance import ExposureSnapshot, build_rebalance_proposal
from ai_pm_agent.autopm.report_writer import (
    POLICY_MANIFEST_JSON,
    REBALANCE_CSV,
    REBALANCE_MD,
    RECOMMENDATIONS_CSV,
    RISK_WARNINGS_MD,
    write_rebalance_report,
)


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "autopm_rebalance" / "sample_inputs.json"


@pytest.fixture
def run_root() -> Iterator[Path]:
    root = Path(".pytest_autopm_rebalance_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        parent = root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _reason() -> list[dict[str, str]]:
    source_hash = str(_fixture()["source_hash"])
    return [
        {
            "code": "AI_REVENUE_MIGRATION_EVIDENCED",
            "backing_type": "source",
            "source_hash": source_hash,
            "evidence_level": "primary_official",
            "source_date": "2026-03-31",
            "period": "2026Q1",
            "field": "ai_revenue_share",
        }
    ]


def _rec(ticker: str = "NEWAI", action: str = "buy", current: float = 0.0, target: float = 3.0, **overrides: object) -> dict[str, object]:
    source_hash = str(_fixture()["source_hash"])
    row = {
        "ticker": ticker,
        "action": action,
        "conviction_score": 0.82,
        "current_weight_pct": current,
        "target_weight_pct": target,
        "delta_weight_pct": round(target - current, 4),
        "max_position_pct": 5.0,
        "valuation_dependent": True,
        "valuation_gate": {"passed": True},
        "valuation_snapshot_present": True,
        "portfolio_gate": {"passed": True},
        "thesis_kill_triggers": ["kill1", "kill2", "kill3"],
        "risk_warnings": [],
        "red_team_warnings": [],
        "blocked": False,
        "executable_proposal": False,
        "source_hashes": [source_hash],
        "reason_codes": _reason(),
        "claim_audit_passed": True,
        "theme": "AI hardware",
        "region": "Asia",
        "sector": "Information Technology",
        "issuer": ticker,
    }
    row.update(overrides)
    return row


def _proposal(recommendations: list[dict[str, object]]):
    return build_rebalance_proposal(
        recommendations,
        as_of_date="2026-06-21",
        starting_cash_pct=10.0,
        exposure_before=ExposureSnapshot(theme={"AI hardware": 28.0}, region={"Asia": 28.0}, sector={"Information Technology": 28.0}),
        policy=AutopmPolicy(sell_allowed=True, max_theme_weight_pct=35.0, max_region_weight_pct=80.0),
    )


def test_report_writer_creates_expected_files_under_tempdir(run_root: Path) -> None:
    recommendations = [_rec()]
    output = write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    for name in [REBALANCE_MD, RECOMMENDATIONS_CSV, REBALANCE_CSV, POLICY_MANIFEST_JSON, RISK_WARNINGS_MD]:
        assert (run_root / name).exists()
        assert str(run_root) in output[next(key for key, value in output.items() if value == str(run_root / name))]
    assert output["validation_status"] == ValidationStatus.VALID.value


def test_output_validator_can_validate_good_fixture_output(run_root: Path) -> None:
    recommendations = [_rec()]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    result = validate_output_dir(run_root, strict=True)

    assert result.status == ValidationStatus.VALID


def test_missing_policy_manifest_invalid(run_root: Path) -> None:
    recommendations = [_rec()]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )
    (run_root / "autopm_policy_manifest.json").unlink()

    result = validate_output_dir(run_root, strict=True)

    assert result.status == ValidationStatus.INVALID


def test_missing_source_manifest_invalid(run_root: Path) -> None:
    recommendations = [_rec()]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )
    (run_root / "autopm_source_manifest.json").unlink()

    result = validate_output_dir(run_root, strict=True)

    assert result.status == ValidationStatus.INVALID


def test_manual_review_rows_remain_not_executed_in_reports(run_root: Path) -> None:
    recommendations = [_rec("REVIEW", "manual_review", 1.0, 1.0, claim_audit_passed=False)]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    payload = json.loads((run_root / "autopm_rebalance_proposal.json").read_text(encoding="utf-8"))
    assert payload["not_executed"] is True
    assert payload["proposed_trades"][0]["not_executed"] is True
    assert payload["proposed_trades"][0]["manual_review_required"] is True


def test_no_broker_execution_artifacts_are_created(run_root: Path) -> None:
    recommendations = [_rec()]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    names = {path.name.lower() for path in run_root.iterdir()}
    assert not any("broker" in name or "execution" in name or "order" in name for name in names)


def test_no_network_access_required(run_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    recommendations = [_rec()]

    output = write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    assert output["validation_status"] == ValidationStatus.VALID.value


def test_rebalance_json_schema_version_and_not_executed(run_root: Path) -> None:
    recommendations = [_rec()]
    write_rebalance_report(
        run_root,
        recommendations=recommendations,
        proposal=_proposal(recommendations),
        policy_manifest=_fixture()["policy_manifest"],
        source_manifest=_fixture()["source_manifest"],
    )

    payload = json.loads((run_root / "autopm_rebalance_proposal.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == AUTOPM_SCHEMA_VERSION
    assert payload["not_executed"] is True
    assert all(row["not_executed"] is True for row in payload["proposed_trades"])

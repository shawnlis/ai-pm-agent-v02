from __future__ import annotations

from pathlib import Path
import shutil
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import AutopmMode
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.portfolio_loader import AutopmPortfolioLoaderError, load_autopm_portfolio
from ai_pm_agent.autopm.portfolio_policy import (
    AutopmPortfolioPolicy,
    CandidatePortfolioMetadata,
    compute_portfolio_policy_context,
    evaluate_portfolio_gate,
    trim_or_sell_allowed,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "autopm_recommender"


@pytest.fixture
def local_tmp_path() -> Path:
    temp_root = Path(".pytest_autopm_pr7_tmp")
    path = temp_root / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()


def _policy(**overrides: object) -> AutopmPortfolioPolicy:
    base = AutopmPolicy(
        mode=AutopmMode.PROPOSAL,
        max_single_name_weight_pct=5.0,
        max_theme_weight_pct=35.0,
        max_region_weight_pct=80.0,
        max_leverage_adjusted_exposure_pct=120.0,
        min_cash_pct=2.0,
        max_new_position_pct=3.0,
        max_add_pct_per_run=2.0,
        trim_threshold_pct=1.0,
        sell_allowed=bool(overrides.pop("sell_allowed", False)),
    )
    return AutopmPortfolioPolicy(
        base_policy=base,
        max_sector_weight_pct=float(overrides.pop("max_sector_weight_pct", 60.0)),
        max_issuer_weight_pct=float(overrides.pop("max_issuer_weight_pct", 8.0)),
    )


def test_portfolio_loaded_from_json_fixture() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.json")

    assert snapshot.as_of_date.isoformat() == "2026-06-20"
    assert snapshot.total_base_equity_value == 100.0
    assert snapshot.cash == 10.0
    assert {holding.ticker for holding in snapshot.holdings} >= {"UNDER", "OVER"}


def test_portfolio_loaded_from_csv_fixture() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.csv")

    assert snapshot.total_base_equity_value == 20.0
    assert snapshot.cash == 10.0
    assert snapshot.base_market_value_weights["OVER"] == 0.4


def test_real_data_looking_paths_fail_closed_before_reading(local_tmp_path: Path) -> None:
    for name in ["portfolio.csv", "IBKR Positions.csv", "broker_export.json", "client_account_statement.json"]:
        path = local_tmp_path / name
        path.write_text("not read", encoding="utf-8")
        with pytest.raises(AutopmPortfolioLoaderError):
            load_autopm_portfolio(path)


def test_current_weights_and_exposures_computed() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.json")
    context = compute_portfolio_policy_context(
        snapshot,
        CandidatePortfolioMetadata(
            ticker="UNDER",
            theme="AI hardware",
            region="Asia",
            sector="Information Technology",
            issuer="UNDER_ISSUER",
        ),
        policy=_policy(),
    )

    assert context.current_weight_pct == 2.0
    assert context.cash_pct == 10.0
    assert context.theme_exposure_pct == 28.0
    assert context.region_exposure_pct == 28.0
    assert context.sector_exposure_pct == 28.0
    assert context.issuer_exposure_pct == 2.0


def test_concentration_blocks_add() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.json")
    gate = evaluate_portfolio_gate(
        snapshot,
        CandidatePortfolioMetadata(ticker="OVER", theme="AI hardware", region="Asia", sector="Information Technology", issuer="OVER_ISSUER"),
        proposed_target_weight_pct=11.0,
        policy=_policy(),
    )

    assert gate.passed is False
    assert "MAX_SINGLE_NAME_EXCEEDED" in gate.concentration_warnings
    assert "MAX_ADD_PER_RUN_EXCEEDED" in gate.concentration_warnings


def test_max_theme_exposure_blocks_add() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.json")
    gate = evaluate_portfolio_gate(
        snapshot,
        CandidatePortfolioMetadata(ticker="NEWAI", theme="AI hardware", region="Asia", sector="Information Technology", issuer="NEWAI"),
        proposed_target_weight_pct=3.0,
        policy=_policy(),
    )

    assert gate.passed is True

    blocked = evaluate_portfolio_gate(
        snapshot,
        CandidatePortfolioMetadata(ticker="NEWAI", theme="AI hardware", region="Asia", sector="Information Technology", issuer="NEWAI"),
        proposed_target_weight_pct=3.0,
        policy=AutopmPortfolioPolicy(base_policy=AutopmPolicy(mode=AutopmMode.PROPOSAL, max_theme_weight_pct=30.0), max_sector_weight_pct=60.0),
    )
    assert blocked.passed is False
    assert "THEME_EXPOSURE_LIMIT_EXCEEDED" in blocked.concentration_warnings


def test_cash_constraint_blocks_new_buy() -> None:
    snapshot = load_autopm_portfolio(FIXTURE_DIR / "sample_autopm_portfolio.json")
    gate = evaluate_portfolio_gate(
        snapshot,
        CandidatePortfolioMetadata(ticker="NEWAI", theme="new theme", region="Asia", sector="Information Technology", issuer="NEWAI"),
        proposed_target_weight_pct=3.0,
        policy=AutopmPortfolioPolicy(base_policy=AutopmPolicy(mode=AutopmMode.PROPOSAL, min_cash_pct=8.0), max_sector_weight_pct=60.0),
    )

    assert gate.passed is False
    assert "MIN_CASH_LIMIT_EXCEEDED" in gate.concentration_warnings


def test_trim_allowed_only_if_configured() -> None:
    assert trim_or_sell_allowed(_policy(sell_allowed=False)) is False
    assert trim_or_sell_allowed(_policy(sell_allowed=True)) is True


def test_no_legacy_pm_prompt_import_or_broker_execution_import() -> None:
    for path in Path("src/ai_pm_agent/autopm").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "build_pm_prompt" not in text
        for line in text.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")):
                assert "broker" not in stripped
                assert "ibkr" not in stripped
                assert "execution" not in stripped

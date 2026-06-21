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

from ai_pm_agent.autopm.paper_portfolio import (
    PaperPortfolioError,
    apply_rebalance_proposal,
    assert_fixture_path,
    load_fixture_prices,
    load_paper_state,
    write_paper_state,
)


FIXTURE = ROOT / "tests" / "fixtures" / "autopm_paper_portfolio"


def _proposal() -> dict:
    payload = json.loads((FIXTURE / "proposal.json").read_text(encoding="utf-8"))
    payload.pop("fixture_only", None)
    return payload


def test_paper_portfolio_consumes_proposal_rows() -> None:
    state = load_paper_state(FIXTURE / "initial_state.json")
    prices = load_fixture_prices(FIXTURE / "prices.json")

    updated = apply_rebalance_proposal(state, _proposal(), prices)

    assert "NEWAI" in updated.holdings
    assert updated.transaction_log
    assert updated.simulated is True
    assert updated.not_broker_execution is True


def test_rejects_proposal_missing_not_executed_true() -> None:
    state = load_paper_state(FIXTURE / "initial_state.json")
    prices = load_fixture_prices(FIXTURE / "prices.json")
    proposal = _proposal()
    proposal["proposed_trades"][0]["not_executed"] = False

    with pytest.raises(PaperPortfolioError, match="not_executed"):
        apply_rebalance_proposal(state, proposal, prices)


def test_paper_records_include_simulated_and_not_broker_execution(tmp_path: Path) -> None:
    state = load_paper_state(FIXTURE / "initial_state.json")
    prices = load_fixture_prices(FIXTURE / "prices.json")
    updated = apply_rebalance_proposal(state, _proposal(), prices)

    out = tmp_path / "paper_state.json"
    write_paper_state(updated, out)
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["simulated"] is True
    assert payload["not_broker_execution"] is True
    assert all(row["simulated"] is True and row["not_broker_execution"] is True for row in payload["transaction_log"])
    assert any(row["realized_pnl"] < 0 for row in payload["transaction_log"] if row["action"] == "trim")


def test_paper_portfolio_updates_cash_and_holdings() -> None:
    state = load_paper_state(FIXTURE / "initial_state.json")
    prices = load_fixture_prices(FIXTURE / "prices.json")
    updated = apply_rebalance_proposal(state, _proposal(), prices)

    assert updated.cash == 9000.0
    assert updated.holdings["NEWAI"].quantity == 40.0
    assert updated.holdings["NEWAI"].average_cost == 50.0
    assert updated.holdings["BASE"].quantity < 100.0


def test_missing_price_fails_closed() -> None:
    state = load_paper_state(FIXTURE / "initial_state.json")
    prices = {("2026-02-28", "BASE"): 95.0}

    with pytest.raises(PaperPortfolioError, match="missing fixture price"):
        apply_rebalance_proposal(state, _proposal(), prices)


def test_broker_client_account_paths_rejected(tmp_path: Path) -> None:
    risky = tmp_path / "client_account_prices.json"
    risky.write_text('{"fixture_only": true, "prices": []}', encoding="utf-8")

    with pytest.raises(PaperPortfolioError, match="refusing"):
        assert_fixture_path(risky)


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert load_fixture_prices(FIXTURE / "prices.json")


def test_no_broker_execution_imports() -> None:
    text = (SRC / "ai_pm_agent" / "autopm" / "paper_portfolio.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("import ", "from ")):
            assert "broker" not in stripped
            assert "ibkr" not in stripped
            assert "execution" not in stripped

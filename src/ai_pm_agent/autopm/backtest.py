"""Deterministic fixture-only autopm backtest harness."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.autopm.paper_portfolio import (
    PaperPortfolioError,
    PaperPortfolioState,
    apply_rebalance_proposal,
    assert_fixture_path,
    load_fixture_prices,
    load_paper_state,
    mark_to_market,
)


class AutopmBacktestError(ValueError):
    """Raised when fixture backtest inputs fail closed."""


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    portfolio_values: tuple[dict[str, object], ...]
    cash: float
    turnover: float
    realized_pnl: float
    unrealized_pnl: float
    max_drawdown: float
    hit_rate: float
    benchmark_return: float | None
    exposure_by_theme: dict[str, float] = field(default_factory=dict)
    exposure_by_region: dict[str, float] = field(default_factory=dict)
    recommendation_outcome_summary: dict[str, object] = field(default_factory=dict)
    simulated: bool = True
    not_broker_execution: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "portfolio_values": list(self.portfolio_values),
            "cash": round(self.cash, 4),
            "turnover": round(self.turnover, 6),
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "max_drawdown": round(self.max_drawdown, 6),
            "hit_rate": round(self.hit_rate, 6),
            "benchmark_return": None if self.benchmark_return is None else round(self.benchmark_return, 6),
            "exposure_by_theme": self.exposure_by_theme,
            "exposure_by_region": self.exposure_by_region,
            "recommendation_outcome_summary": self.recommendation_outcome_summary,
            "simulated": self.simulated,
            "not_broker_execution": self.not_broker_execution,
        }


def run_backtest_from_fixture(path: str | Path) -> BacktestResult:
    """Run a deterministic paper backtest from a single fixture specification."""

    fixture_path = assert_fixture_path(path)
    payload = _load_fixture(fixture_path)
    base_dir = fixture_path.parent
    prices = load_fixture_prices(base_dir / _required_text(payload, "prices_file"))
    state = load_paper_state(base_dir / _required_text(payload, "initial_state_file"))
    run_id = _text(payload.get("run_id")) or "autopm-backtest-fixture"
    records = [_value_record(state)]
    turnover_notional = 0.0

    for event in _list(payload.get("rebalance_events")):
        rebalance_date = _required_text(event, "date")
        proposal = _dict(event.get("proposal"))
        if not proposal:
            raise AutopmBacktestError("rebalance event requires proposal")
        _reject_lookahead(proposal, rebalance_date)
        before_transactions = len(state.transaction_log)
        try:
            state = apply_rebalance_proposal(state, proposal, prices, as_of_date=rebalance_date)
            state = mark_to_market(state, prices, rebalance_date)
        except PaperPortfolioError as exc:
            raise AutopmBacktestError(str(exc)) from exc
        for transaction in state.transaction_log[before_transactions:]:
            turnover_notional += abs(transaction.notional)
        records.append(_value_record(state))

    for valuation_date in _string_list(payload.get("valuation_dates")):
        if records and records[-1]["date"] == valuation_date:
            continue
        try:
            state = mark_to_market(state, prices, valuation_date)
        except PaperPortfolioError as exc:
            raise AutopmBacktestError(str(exc)) from exc
        records.append(_value_record(state))

    initial_value = float(records[0]["portfolio_value"]) if records else 0.0
    final_value = float(records[-1]["portfolio_value"]) if records else 0.0
    return BacktestResult(
        run_id=run_id,
        portfolio_values=tuple(records),
        cash=state.cash,
        turnover=0.0 if initial_value == 0 else turnover_notional / initial_value,
        realized_pnl=_realized_pnl(state),
        unrealized_pnl=_unrealized_pnl(state),
        max_drawdown=_max_drawdown([float(row["portfolio_value"]) for row in records]),
        hit_rate=_hit_rate(_list(payload.get("recommendation_outcomes"))),
        benchmark_return=_benchmark_return(_list(payload.get("benchmark"))),
        exposure_by_theme=_exposure(state, "theme"),
        exposure_by_region=_exposure(state, "region"),
        recommendation_outcome_summary=_recommendation_summary(_list(payload.get("recommendation_outcomes"))),
    )


def write_backtest_result(result: BacktestResult, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AutopmBacktestError("backtest fixture must contain an object")
    if payload.get("fixture_only") is not True:
        raise AutopmBacktestError("backtest inputs must declare fixture_only=true")
    return payload


def _reject_lookahead(value: Any, rebalance_date: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_date", "price_date", "available_date", "as_of_date"} and _text(item) > rebalance_date:
                raise AutopmBacktestError(f"lookahead field {key}={item} after rebalance date {rebalance_date}")
            _reject_lookahead(item, rebalance_date)
    elif isinstance(value, list):
        for item in value:
            _reject_lookahead(item, rebalance_date)


def _value_record(state: PaperPortfolioState) -> dict[str, object]:
    return {
        "date": state.as_of_date,
        "portfolio_value": round(state.portfolio_value, 4),
        "cash": round(state.cash, 4),
        "holdings_value": round(state.holdings_value, 4),
    }


def _realized_pnl(state: PaperPortfolioState) -> float:
    return sum(transaction.realized_pnl for transaction in state.transaction_log)


def _unrealized_pnl(state: PaperPortfolioState) -> float:
    pnl = 0.0
    for holding in state.holdings.values():
        average_cost = holding.average_cost if holding.average_cost is not None else holding.last_price
        pnl += (holding.last_price - average_cost) * holding.quantity
    return pnl


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd


def _hit_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    hits = sum(1 for row in rows if _bool(row.get("hit")))
    return hits / len(rows)


def _benchmark_return(rows: list[dict[str, Any]]) -> float | None:
    if len(rows) < 2:
        return None
    ordered = sorted(rows, key=lambda row: _text(row.get("date")))
    start = _float(ordered[0].get("value"))
    end = _float(ordered[-1].get("value"))
    if start == 0:
        return None
    return (end - start) / start


def _recommendation_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "count": len(rows),
        "hit_count": sum(1 for row in rows if _bool(row.get("hit"))),
        "miss_count": sum(1 for row in rows if not _bool(row.get("hit"))),
    }


def _exposure(state: PaperPortfolioState, field_name: str) -> dict[str, float]:
    total = state.portfolio_value
    if total == 0:
        return {}
    exposure: dict[str, float] = {}
    for holding in state.holdings.values():
        key = getattr(holding, field_name)
        if not key:
            continue
        exposure[key] = exposure.get(key, 0.0) + holding.market_value / total
    return {key: round(value, 6) for key, value in sorted(exposure.items())}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text(row.get(key))
    if not value:
        raise AutopmBacktestError(f"required value missing: {key}")
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}

"""Paper-only portfolio simulation for autopm rebalance proposals.

This module consumes proposal rows and fixture prices. It does not connect to
brokers, submit orders, fetch live data, or create execution artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


DISALLOWED_PATH_TERMS = ("portfolio.csv", "ibkr", "broker", "client", "account", "statement")
TRADE_ACTIONS = {"buy", "add", "trim", "sell"}


class PaperPortfolioError(ValueError):
    """Raised when a paper portfolio simulation fails closed."""


@dataclass(frozen=True)
class PaperHolding:
    ticker: str
    quantity: float
    last_price: float
    theme: str = ""
    region: str = ""
    average_cost: float | None = None

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "quantity": round(self.quantity, 8),
            "last_price": round(self.last_price, 6),
            "average_cost": None if self.average_cost is None else round(self.average_cost, 6),
            "market_value": round(self.market_value, 4),
            "theme": self.theme,
            "region": self.region,
        }


@dataclass(frozen=True)
class PaperTransaction:
    date: str
    ticker: str
    action: str
    quantity_delta: float
    price: float
    notional: float
    simulated: bool = True
    not_broker_execution: bool = True
    source: str = "autopm_rebalance_proposal"
    realized_pnl: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "action": self.action,
            "quantity_delta": round(self.quantity_delta, 8),
            "price": round(self.price, 6),
            "notional": round(self.notional, 4),
            "simulated": self.simulated,
            "not_broker_execution": self.not_broker_execution,
            "source": self.source,
            "realized_pnl": round(self.realized_pnl, 4),
        }


@dataclass(frozen=True)
class PaperPortfolioState:
    as_of_date: str
    cash: float
    holdings: dict[str, PaperHolding] = field(default_factory=dict)
    transaction_log: tuple[PaperTransaction, ...] = ()
    simulated: bool = True
    not_broker_execution: bool = True

    @property
    def holdings_value(self) -> float:
        return sum(holding.market_value for holding in self.holdings.values())

    @property
    def portfolio_value(self) -> float:
        return self.cash + self.holdings_value

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of_date": self.as_of_date,
            "cash": round(self.cash, 4),
            "holdings_value": round(self.holdings_value, 4),
            "portfolio_value": round(self.portfolio_value, 4),
            "holdings": [holding.to_dict() for holding in sorted(self.holdings.values(), key=lambda item: item.ticker)],
            "transaction_log": [transaction.to_dict() for transaction in self.transaction_log],
            "simulated": self.simulated,
            "not_broker_execution": self.not_broker_execution,
        }


def assert_fixture_path(path: str | Path) -> Path:
    """Reject live/private-looking paths before reading fixture content."""

    candidate = Path(path)
    lowered = str(candidate).lower()
    if any(term in lowered for term in DISALLOWED_PATH_TERMS):
        raise PaperPortfolioError("refusing broker/client/account/private-looking path")
    if not candidate.exists() or not candidate.is_file():
        raise PaperPortfolioError(f"fixture file not found: {candidate}")
    return candidate


def load_fixture_prices(path: str | Path) -> dict[tuple[str, str], float]:
    """Load fixture-only prices keyed by (date, ticker)."""

    payload = _load_json(assert_fixture_path(path))
    rows = _list(payload.get("prices"))
    if not rows:
        raise PaperPortfolioError("price fixture requires non-empty prices")
    prices: dict[tuple[str, str], float] = {}
    for row in rows:
        date = _required_text(row, "date")
        ticker = _required_text(row, "ticker").upper()
        price = _float(row.get("price"))
        if price <= 0:
            raise PaperPortfolioError(f"missing required positive price for {ticker} on {date}")
        prices[(date, ticker)] = price
    return prices


def load_paper_state(path: str | Path) -> PaperPortfolioState:
    """Load an initial paper-only state from a fixture JSON file."""

    payload = _load_json(assert_fixture_path(path))
    holdings = {
        _required_text(row, "ticker").upper(): PaperHolding(
            ticker=_required_text(row, "ticker").upper(),
            quantity=_float(row.get("quantity")),
            last_price=_float(row.get("last_price")),
            theme=_text(row.get("theme")),
            region=_text(row.get("region")),
            average_cost=_float(row.get("average_cost")) or _float(row.get("last_price")),
        )
        for row in _list(payload.get("holdings"))
    }
    if any(holding.last_price <= 0 for holding in holdings.values()):
        raise PaperPortfolioError("paper state holdings require positive last_price")
    return PaperPortfolioState(
        as_of_date=_required_text(payload, "as_of_date"),
        cash=_float(payload.get("cash")),
        holdings=holdings,
    )


def apply_rebalance_proposal(
    state: PaperPortfolioState,
    proposal: dict[str, Any],
    prices: dict[tuple[str, str], float],
    *,
    as_of_date: str | None = None,
) -> PaperPortfolioState:
    """Apply non-executed proposal rows as paper simulation fills."""

    if proposal.get("not_executed") is not True:
        raise PaperPortfolioError("rebalance proposal must set not_executed=true")
    trade_date = as_of_date or _required_text(proposal, "as_of_date")
    holdings = {ticker: PaperHolding(**holding.__dict__) for ticker, holding in state.holdings.items()}
    cash = state.cash
    transactions = list(state.transaction_log)

    for row in _list(proposal.get("proposed_trades")):
        if row.get("not_executed") is not True:
            raise PaperPortfolioError("proposal row must set not_executed=true")
        if row.get("executable_proposal") is False or row.get("manual_review_required") is True or row.get("blocked") is True:
            continue
        action = _text(row.get("action")).lower()
        if action not in TRADE_ACTIONS:
            continue
        ticker = _required_text(row, "ticker").upper()
        price = prices.get((trade_date, ticker))
        if price is None:
            raise PaperPortfolioError(f"missing fixture price for {ticker} on {trade_date}")
        notional = _float(row.get("estimated_notional"))
        if action in {"buy", "add"} and notional <= 0:
            notional = max(0.0, _float(row.get("delta_weight_pct"))) / 100.0 * state.portfolio_value
        if action in {"trim", "sell"} and notional >= 0:
            notional = -abs(_float(row.get("delta_weight_pct")) / 100.0 * state.portfolio_value)
        if abs(notional) == 0:
            continue
        quantity_delta = notional / price
        existing = holdings.get(ticker, PaperHolding(ticker=ticker, quantity=0.0, last_price=price, theme=_text(row.get("theme")), region=_text(row.get("region")), average_cost=price))
        if existing.quantity + quantity_delta < -1e-9:
            raise PaperPortfolioError(f"paper trade would create negative holding for {ticker}")
        average_cost = existing.average_cost or price
        realized_pnl = 0.0
        if quantity_delta > 0:
            new_quantity = existing.quantity + quantity_delta
            average_cost = ((existing.quantity * average_cost) + (quantity_delta * price)) / new_quantity if new_quantity else price
        elif quantity_delta < 0:
            realized_pnl = (price - average_cost) * abs(quantity_delta)
        holdings[ticker] = PaperHolding(
            ticker=ticker,
            quantity=max(0.0, existing.quantity + quantity_delta),
            last_price=price,
            theme=existing.theme or _text(row.get("theme")),
            region=existing.region or _text(row.get("region")),
            average_cost=average_cost,
        )
        cash -= notional
        transactions.append(PaperTransaction(date=trade_date, ticker=ticker, action=action, quantity_delta=quantity_delta, price=price, notional=notional, realized_pnl=realized_pnl))

    return PaperPortfolioState(
        as_of_date=trade_date,
        cash=round(cash, 4),
        holdings={ticker: holding for ticker, holding in holdings.items() if holding.quantity > 1e-9},
        transaction_log=tuple(transactions),
    )


def mark_to_market(state: PaperPortfolioState, prices: dict[tuple[str, str], float], as_of_date: str) -> PaperPortfolioState:
    """Mark holdings to fixture prices for a date, failing closed if missing."""

    holdings: dict[str, PaperHolding] = {}
    for ticker, holding in state.holdings.items():
        price = prices.get((as_of_date, ticker))
        if price is None:
            raise PaperPortfolioError(f"missing fixture price for {ticker} on {as_of_date}")
        holdings[ticker] = PaperHolding(ticker=ticker, quantity=holding.quantity, last_price=price, theme=holding.theme, region=holding.region, average_cost=holding.average_cost)
    return PaperPortfolioState(
        as_of_date=as_of_date,
        cash=state.cash,
        holdings=holdings,
        transaction_log=state.transaction_log,
    )


def write_paper_state(state: PaperPortfolioState, path: str | Path) -> None:
    """Write paper state artifacts under an explicitly provided path."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperPortfolioError("fixture JSON must contain an object")
    if payload.get("fixture_only") is not True:
        raise PaperPortfolioError("paper/backtest inputs must declare fixture_only=true")
    return payload


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text(row.get(key))
    if not value:
        raise PaperPortfolioError(f"required value missing: {key}")
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

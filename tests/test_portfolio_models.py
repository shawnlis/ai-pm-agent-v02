from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.portfolio.fixtures import build_sample_portfolio_snapshot
from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


class HoldingModelTests(unittest.TestCase):
    def test_normal_equity_holding(self) -> None:
        holding = Holding(
            ticker="nvda",
            name="NVIDIA",
            market="NASDAQ",
            quantity=10,
            current_price=120.0,
            asset_class="equity",
            theme=["AI infrastructure"],
            risk_bucket="single_name_growth",
        )

        self.assertEqual(holding.ticker, "NVDA")
        self.assertEqual(holding.currency, "USD")
        self.assertEqual(holding.market_value, 1200.0)
        self.assertEqual(holding.leverage_multiplier, 1.0)
        self.assertTrue(holding.valuation_complete)

    def test_missing_market_value_uses_current_price(self) -> None:
        holding = Holding(ticker="MSFT", quantity=4, current_price=450.0)

        self.assertEqual(holding.market_value, 1800.0)
        self.assertTrue(holding.valuation_complete)

    def test_missing_market_value_and_price_is_allowed(self) -> None:
        holding = Holding(ticker="PRIVATE", quantity=5, market_value=None, current_price=None)

        self.assertIsNone(holding.market_value)
        self.assertFalse(holding.valuation_complete)

    def test_leveraged_etfs_default_to_three_times(self) -> None:
        for ticker in ("TQQQ", "SOXL"):
            with self.subTest(ticker=ticker):
                holding = Holding(ticker=ticker, quantity=10, current_price=50.0)
                self.assertEqual(holding.leverage_multiplier, 3.0)

    def test_explicit_leverage_multiplier_is_preserved(self) -> None:
        holding = Holding(ticker="TQQQ", quantity=10, current_price=50.0, leverage_multiplier=2.0)

        self.assertEqual(holding.leverage_multiplier, 2.0)

    def test_etha_defaults_to_crypto_beta_not_ai_equity(self) -> None:
        holding = Holding(ticker="ETHA", quantity=100, current_price=30.0)

        self.assertEqual(holding.asset_class, "crypto_etf")
        self.assertIn("crypto beta", holding.theme)
        self.assertEqual(holding.risk_bucket, "crypto_beta")
        self.assertNotEqual(holding.asset_class, "equity")


class PortfolioSnapshotTests(unittest.TestCase):
    def test_computed_totals_cash_and_weights(self) -> None:
        snapshot = PortfolioSnapshot(
            as_of_date="2026-06-06",
            base_currency="usd",
            cash=500.0,
            cash_currency="usd",
            holdings=[
                Holding(ticker="NVDA", quantity=10, current_price=100.0),
                Holding(ticker="MSFT", quantity=5, current_price=100.0),
            ],
        )

        self.assertEqual(snapshot.as_of_date, date(2026, 6, 6))
        self.assertEqual(snapshot.base_currency, "USD")
        self.assertEqual(snapshot.cash_currency, "USD")
        self.assertEqual(snapshot.total_market_value, 1500.0)
        self.assertEqual(snapshot.total_cash, 500.0)
        self.assertEqual(snapshot.total_equity_value, 2000.0)
        self.assertAlmostEqual(snapshot.holding_weights["NVDA"], 0.5)
        self.assertAlmostEqual(snapshot.holding_weights["MSFT"], 0.25)

    def test_identifies_incomplete_valuation_holdings(self) -> None:
        snapshot = PortfolioSnapshot(
            as_of_date="2026-06-06",
            holdings=[
                Holding(ticker="NVDA", quantity=10, current_price=100.0),
                Holding(ticker="MISSING", quantity=5),
            ],
        )

        self.assertEqual(snapshot.incomplete_valuation_holdings, ["MISSING"])

    def test_fixture_contains_core_holdings_and_cash(self) -> None:
        snapshot = build_sample_portfolio_snapshot()
        tickers = {holding.ticker for holding in snapshot.holdings}

        self.assertGreater(snapshot.cash, 0)
        self.assertEqual(snapshot.cash_currency, "USD")
        self.assertTrue({"TQQQ", "SOXL", "NVDA", "7709.HK", "MU", "GOOGL", "MSFT", "TSLA", "ETHA"}.issubset(tickers))
        self.assertEqual(next(holding for holding in snapshot.holdings if holding.ticker == "TQQQ").leverage_multiplier, 3.0)
        self.assertEqual(next(holding for holding in snapshot.holdings if holding.ticker == "SOXL").leverage_multiplier, 3.0)


if __name__ == "__main__":
    unittest.main()

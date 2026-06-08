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
from ai_pm_agent.portfolio.models import Holding, LookThroughComponent, PortfolioSnapshot


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

    def test_optional_metadata_fields_are_preserved(self) -> None:
        holding = Holding(
            ticker="9988.hk",
            quantity=80,
            market_value_local=800.0,
            trading_currency="hkd",
            base_currency="usd",
            fx_rate_to_base=0.125,
            instrument_type="stock",
            issuer_name="Alibaba Group",
            issuer_canonical_id="ALIBABA",
            underlying_ticker="baba",
            listing_country="Hong Kong",
            country_of_risk="China",
            region="Asia",
            sector="Consumer Discretionary",
            industry="Internet Retail",
            themes=["cloud AI", "China internet"],
        )

        self.assertEqual(holding.ticker, "9988.HK")
        self.assertEqual(holding.currency, "HKD")
        self.assertEqual(holding.trading_currency, "HKD")
        self.assertEqual(holding.base_currency, "USD")
        self.assertEqual(holding.underlying_ticker, "BABA")
        self.assertEqual(holding.market_value, 800.0)
        self.assertEqual(holding.market_value_base, 100.0)
        self.assertEqual(holding.theme, ["cloud AI", "China internet"])
        self.assertEqual(holding.themes, holding.theme)

    def test_leverage_factor_alias_feeds_multiplier(self) -> None:
        holding = Holding(ticker="CUSTOM3X", quantity=1, market_value=100.0, leverage_factor=3.0)

        self.assertEqual(holding.leverage_multiplier, 3.0)
        self.assertEqual(holding.leverage_factor, 3.0)

    def test_manual_lookthrough_component_validation(self) -> None:
        component = LookThroughComponent(
            holding_ticker="tqqq",
            component_issuer_name="NVIDIA",
            component_ticker="nvda",
            component_weight=0.25,
            sector="Information Technology",
            theme=["AI infrastructure"],
        )

        self.assertEqual(component.holding_ticker, "TQQQ")
        self.assertEqual(component.component_ticker, "NVDA")
        self.assertEqual(component.theme, ["AI infrastructure"])

        with self.assertRaises(ValueError):
            LookThroughComponent(component_weight=1.1)

    def test_holding_with_lookthrough_marks_availability(self) -> None:
        holding = Holding(
            ticker="TQQQ",
            quantity=1,
            market_value=100.0,
            lookthrough_components=[
                LookThroughComponent(
                    component_issuer_name="NVIDIA",
                    component_weight=1.0,
                    sector="Information Technology",
                )
            ],
        )

        self.assertTrue(holding.lookthrough_available)


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
        self.assertTrue(
            {
                "TQQQ",
                "SOXL",
                "NVDA",
                "7709.HK",
                "HY9H",
                "MU",
                "GOOGL",
                "MSFT",
                "TSLA",
                "ETHA",
                "SMS",
            }.issubset(tickers)
        )
        self.assertEqual(next(holding for holding in snapshot.holdings if holding.ticker == "TQQQ").leverage_multiplier, 3.0)
        self.assertEqual(next(holding for holding in snapshot.holdings if holding.ticker == "SOXL").leverage_multiplier, 3.0)
        self.assertEqual(next(holding for holding in snapshot.holdings if holding.ticker == "HY9H").issuer_canonical_id, "SK_HYNIX")
        self.assertTrue(next(holding for holding in snapshot.holdings if holding.ticker == "SOXL").lookthrough_available)

    def test_snapshot_metadata_exposure_properties(self) -> None:
        snapshot = PortfolioSnapshot(
            as_of_date="2026-06-06",
            cash=100.0,
            holdings=[
                Holding(
                    ticker="BABA",
                    quantity=1,
                    market_value_base=200.0,
                    issuer_canonical_id="ALIBABA",
                    country_of_risk="China",
                    region="Asia",
                    sector="Consumer Discretionary",
                    industry="Internet Retail",
                    instrument_type="adr",
                ),
                Holding(
                    ticker="9988.HK",
                    quantity=1,
                    market_value_local=800.0,
                    fx_rate_to_base=0.125,
                    currency="HKD",
                    issuer_canonical_id="ALIBABA",
                    country_of_risk="China",
                    region="Asia",
                    sector="Consumer Discretionary",
                    industry="Internet Retail",
                    instrument_type="stock",
                ),
            ],
        )

        self.assertEqual(snapshot.total_base_market_value, 300.0)
        self.assertEqual(snapshot.total_base_equity_value, 400.0)
        self.assertAlmostEqual(snapshot.issuer_exposure["ALIBABA"], 300.0 / 400.0)
        self.assertAlmostEqual(snapshot.country_of_risk_exposure["China"], 300.0 / 400.0)
        self.assertAlmostEqual(snapshot.sector_exposure["Consumer Discretionary"], 300.0 / 400.0)


if __name__ == "__main__":
    unittest.main()

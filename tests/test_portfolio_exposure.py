from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.portfolio.exposure import (
    calculate_asset_class_exposure,
    calculate_currency_exposure,
    calculate_gross_exposure,
    calculate_leverage_adjusted_exposure,
    calculate_market_value,
    calculate_risk_bucket_exposure,
    calculate_theme_exposure,
    calculate_weight,
    find_incomplete_valuation_holdings,
)
from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


class PortfolioExposureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = PortfolioSnapshot(
            as_of_date="2026-06-06",
            cash=500.0,
            holdings=[
                Holding(
                    ticker="TQQQ",
                    quantity=10,
                    current_price=100.0,
                    asset_class="leveraged_etf",
                    theme=["leveraged ETF"],
                    risk_bucket="leveraged_etf",
                ),
                Holding(
                    ticker="NVDA",
                    quantity=5,
                    current_price=100.0,
                    asset_class="equity",
                    theme=["AI infrastructure", "semiconductor"],
                    risk_bucket="single_name_growth",
                ),
                Holding(
                    ticker="7709.HK",
                    quantity=10,
                    current_price=20.0,
                    currency="HKD",
                    asset_class="equity",
                    theme=["HBM", "semiconductor"],
                    risk_bucket="semiconductor_cycle",
                ),
                Holding(ticker="ETHA", quantity=10, current_price=25.0),
                Holding(ticker="MISSING", quantity=1),
            ],
        )

    def test_market_value_and_weight(self) -> None:
        tqqq = self.snapshot.holdings[0]

        self.assertEqual(calculate_market_value(tqqq), 1000.0)
        self.assertAlmostEqual(calculate_weight(tqqq, self.snapshot.total_equity_value), 1000.0 / 2450.0)

    def test_gross_exposure(self) -> None:
        self.assertAlmostEqual(calculate_gross_exposure(self.snapshot), 1950.0 / 2450.0)
        self.assertAlmostEqual(self.snapshot.gross_exposure, 1950.0 / 2450.0)

    def test_leverage_adjusted_exposure(self) -> None:
        expected = (1000.0 * 3.0 + 500.0 + 200.0 + 250.0) / 2450.0

        self.assertAlmostEqual(calculate_leverage_adjusted_exposure(self.snapshot), expected)
        self.assertAlmostEqual(self.snapshot.leverage_adjusted_exposure, expected)

    def test_theme_exposure(self) -> None:
        exposure = calculate_theme_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["leveraged ETF"], 1000.0 / 2450.0)
        self.assertAlmostEqual(exposure["AI infrastructure"], 500.0 / 2450.0)
        self.assertAlmostEqual(exposure["semiconductor"], 700.0 / 2450.0)
        self.assertAlmostEqual(exposure["HBM"], 200.0 / 2450.0)
        self.assertAlmostEqual(exposure["crypto beta"], 250.0 / 2450.0)
        self.assertEqual(exposure, self.snapshot.theme_exposure)

    def test_asset_class_exposure(self) -> None:
        exposure = calculate_asset_class_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["leveraged_etf"], 1000.0 / 2450.0)
        self.assertAlmostEqual(exposure["equity"], 700.0 / 2450.0)
        self.assertAlmostEqual(exposure["crypto_etf"], 250.0 / 2450.0)
        self.assertEqual(exposure, self.snapshot.asset_class_exposure)

    def test_currency_exposure(self) -> None:
        exposure = calculate_currency_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["USD"], 1750.0 / 2450.0)
        self.assertAlmostEqual(exposure["HKD"], 200.0 / 2450.0)
        self.assertEqual(exposure, self.snapshot.currency_exposure)

    def test_risk_bucket_exposure(self) -> None:
        exposure = calculate_risk_bucket_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["leveraged_etf"], 1000.0 / 2450.0)
        self.assertAlmostEqual(exposure["single_name_growth"], 500.0 / 2450.0)
        self.assertAlmostEqual(exposure["semiconductor_cycle"], 200.0 / 2450.0)
        self.assertAlmostEqual(exposure["crypto_beta"], 250.0 / 2450.0)
        self.assertEqual(exposure, self.snapshot.risk_bucket_exposure)

    def test_finds_incomplete_valuation_holdings(self) -> None:
        self.assertEqual(find_incomplete_valuation_holdings(self.snapshot), ["MISSING"])


if __name__ == "__main__":
    unittest.main()

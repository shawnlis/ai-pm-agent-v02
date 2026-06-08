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
    calculate_base_leverage_adjusted_gross_exposure,
    calculate_base_market_value,
    calculate_base_market_value_exposure,
    calculate_concentration_summary,
    calculate_country_of_risk_exposure,
    calculate_currency_exposure,
    calculate_gross_exposure,
    calculate_industry_exposure,
    calculate_instrument_type_exposure,
    calculate_issuer_exposure,
    calculate_leverage_adjusted_exposure,
    calculate_leverage_adjusted_gross_exposure,
    calculate_lookthrough_exposure,
    calculate_lookthrough_sector_exposure,
    calculate_market_value,
    calculate_region_exposure,
    calculate_risk_bucket_exposure,
    calculate_sector_exposure,
    calculate_theme_exposure,
    calculate_weight,
    find_incomplete_valuation_holdings,
)
from ai_pm_agent.portfolio.models import Holding, LookThroughComponent, PortfolioSnapshot


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


class PortfolioMetadataExposureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = PortfolioSnapshot(
            as_of_date="2026-06-08",
            cash=100.0,
            holdings=[
                Holding(
                    ticker="TQQQ",
                    quantity=1,
                    market_value=300.0,
                    market_value_base=300.0,
                    asset_class="leveraged_etf",
                    instrument_type="leveraged_etf",
                    issuer_name="ProShares",
                    issuer_canonical_id="PROSHARES",
                    country_of_risk="United States",
                    region="North America",
                    sector="Diversified",
                    industry="Leveraged ETF",
                    theme=["leveraged ETF", "mega-cap tech"],
                    risk_bucket="leveraged_etf",
                    leverage_factor=3.0,
                    lookthrough_components=[
                        LookThroughComponent(
                            component_issuer_name="NVIDIA",
                            component_issuer_canonical_id="NVIDIA",
                            component_ticker="NVDA",
                            component_weight=0.4,
                            sector="Information Technology",
                            industry="Semiconductors",
                            country_of_risk="United States",
                            region="North America",
                            theme=["AI infrastructure", "semiconductor"],
                        ),
                        LookThroughComponent(
                            component_issuer_name="Alphabet",
                            component_issuer_canonical_id="ALPHABET",
                            component_ticker="GOOGL",
                            component_weight=0.6,
                            sector="Communication Services",
                            industry="Internet Content and Information",
                            country_of_risk="United States",
                            region="North America",
                            theme=["cloud AI", "mega-cap tech"],
                        ),
                    ],
                ),
                Holding(
                    ticker="BABA",
                    quantity=1,
                    market_value=200.0,
                    market_value_base=200.0,
                    asset_class="adr",
                    instrument_type="adr",
                    issuer_name="Alibaba Group",
                    issuer_canonical_id="ALIBABA",
                    underlying_ticker="9988.HK",
                    country_of_risk="China",
                    region="Asia",
                    sector="Consumer Discretionary",
                    industry="Internet Retail",
                    theme=["cloud AI", "China internet"],
                    risk_bucket="china_adr",
                ),
                Holding(
                    ticker="9988.HK",
                    quantity=1,
                    market_value_local=800.0,
                    fx_rate_to_base=0.125,
                    currency="HKD",
                    asset_class="equity",
                    instrument_type="stock",
                    issuer_name="Alibaba Group",
                    issuer_canonical_id="ALIBABA",
                    underlying_ticker="BABA",
                    country_of_risk="China",
                    region="Asia",
                    sector="Consumer Discretionary",
                    industry="Internet Retail",
                    theme=["cloud AI", "China internet"],
                    risk_bucket="china_equity",
                ),
                Holding(
                    ticker="HY9H",
                    quantity=1,
                    market_value=150.0,
                    market_value_base=150.0,
                    asset_class="gds",
                    instrument_type="gds",
                    issuer_name="SK Hynix",
                    issuer_canonical_id="SK_HYNIX",
                    underlying_ticker="000660.KS",
                    country_of_risk="South Korea",
                    region="Asia",
                    sector="Information Technology",
                    industry="Semiconductors",
                    theme=["HBM", "semiconductor", "AI infrastructure"],
                    risk_bucket="semiconductor_cycle",
                ),
                Holding(
                    ticker="ETHA",
                    quantity=1,
                    market_value=50.0,
                    market_value_base=50.0,
                    lookthrough_components=[
                        LookThroughComponent(
                            component_issuer_name="Ethereum",
                            component_issuer_canonical_id="ETHEREUM",
                            component_ticker="ETH",
                            component_weight=1.0,
                            sector="Digital Assets",
                            industry="Crypto asset",
                            country_of_risk="Global",
                            region="Global",
                            theme=["crypto beta"],
                            instrument_type="crypto",
                        )
                    ],
                ),
            ],
        )

    def test_base_market_value_exposure_uses_supplied_fake_fx(self) -> None:
        hong_kong_holding = next(holding for holding in self.snapshot.holdings if holding.ticker == "9988.HK")

        self.assertEqual(calculate_base_market_value(hong_kong_holding), 100.0)
        exposure = calculate_base_market_value_exposure(self.snapshot)
        self.assertAlmostEqual(exposure["9988.HK"], 100.0 / 900.0)
        self.assertEqual(list(exposure), sorted(exposure))

    def test_metadata_bucket_exposures(self) -> None:
        self.assertAlmostEqual(calculate_sector_exposure(self.snapshot)["Consumer Discretionary"], 300.0 / 900.0)
        self.assertAlmostEqual(calculate_sector_exposure(self.snapshot)["Information Technology"], 150.0 / 900.0)
        self.assertAlmostEqual(calculate_industry_exposure(self.snapshot)["Internet Retail"], 300.0 / 900.0)
        self.assertAlmostEqual(calculate_region_exposure(self.snapshot)["Asia"], 450.0 / 900.0)
        self.assertAlmostEqual(calculate_country_of_risk_exposure(self.snapshot)["China"], 300.0 / 900.0)
        self.assertAlmostEqual(calculate_country_of_risk_exposure(self.snapshot)["South Korea"], 150.0 / 900.0)

    def test_issuer_grouping_combines_adr_gds_and_local_listing(self) -> None:
        exposure = calculate_issuer_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["ALIBABA"], 300.0 / 900.0)
        self.assertAlmostEqual(exposure["SK_HYNIX"], 150.0 / 900.0)
        self.assertEqual(exposure, self.snapshot.issuer_exposure)

    def test_instrument_type_and_theme_exposures(self) -> None:
        instrument_exposure = calculate_instrument_type_exposure(self.snapshot)
        theme_exposure = calculate_theme_exposure(self.snapshot)

        self.assertAlmostEqual(instrument_exposure["leveraged_etf"], 300.0 / 900.0)
        self.assertAlmostEqual(instrument_exposure["adr"], 200.0 / 900.0)
        self.assertAlmostEqual(instrument_exposure["stock"], 100.0 / 900.0)
        self.assertAlmostEqual(instrument_exposure["gds"], 150.0 / 900.0)
        self.assertAlmostEqual(instrument_exposure["crypto_etf"], 50.0 / 900.0)
        self.assertIn("AI infrastructure", theme_exposure)

    def test_leverage_adjusted_exposure_uses_leverage_factor(self) -> None:
        expected = (300.0 * 3.0 + 200.0 + 800.0 + 150.0 + 50.0) / self.snapshot.total_equity_value
        expected_base = (300.0 * 3.0 + 200.0 + 100.0 + 150.0 + 50.0) / 900.0

        self.assertAlmostEqual(calculate_leverage_adjusted_exposure(self.snapshot), expected)
        self.assertAlmostEqual(calculate_leverage_adjusted_gross_exposure(self.snapshot), expected)
        self.assertAlmostEqual(calculate_base_leverage_adjusted_gross_exposure(self.snapshot), expected_base)

    def test_manual_lookthrough_exposure_with_line_item_fallback(self) -> None:
        exposure = calculate_lookthrough_sector_exposure(self.snapshot)

        self.assertAlmostEqual(exposure["Communication Services"], 180.0 / 900.0)
        self.assertAlmostEqual(exposure["Consumer Discretionary"], 300.0 / 900.0)
        self.assertAlmostEqual(exposure["Digital Assets"], 50.0 / 900.0)
        self.assertAlmostEqual(exposure["Information Technology"], 270.0 / 900.0)
        self.assertEqual(list(exposure), sorted(exposure))

    def test_manual_lookthrough_exposure_without_fallback(self) -> None:
        exposure = calculate_lookthrough_exposure(self.snapshot, "sector", fallback_to_line_item=False)

        self.assertAlmostEqual(exposure["Communication Services"], 180.0 / 900.0)
        self.assertAlmostEqual(exposure["Digital Assets"], 50.0 / 900.0)
        self.assertAlmostEqual(exposure["Information Technology"], 120.0 / 900.0)
        self.assertNotIn("Consumer Discretionary", exposure)

    def test_concentration_summary_is_deterministic(self) -> None:
        summary = calculate_concentration_summary(self.snapshot, top_n=2)

        self.assertEqual(summary["holding_count"], 5)
        self.assertEqual(summary["total_base_equity_value"], 900.0)
        self.assertEqual(summary["largest_holding"]["ticker"], "TQQQ")
        self.assertEqual(summary["largest_issuer"]["issuer"], "ALIBABA")
        self.assertEqual([row["ticker"] for row in summary["top_holdings"]], ["TQQQ", "BABA"])

    def test_empty_portfolio_and_missing_metadata_are_safe(self) -> None:
        empty = PortfolioSnapshot(as_of_date="2026-06-08")
        sparse = PortfolioSnapshot(
            as_of_date="2026-06-08",
            holdings=[Holding(ticker="MISSINGMETA", quantity=1, market_value=100.0)],
        )

        self.assertEqual(calculate_sector_exposure(empty), {})
        self.assertEqual(calculate_lookthrough_sector_exposure(empty), {})
        self.assertIsNone(calculate_concentration_summary(empty)["largest_holding"])
        self.assertEqual(calculate_sector_exposure(sparse), {})
        self.assertEqual(calculate_region_exposure(sparse), {})


if __name__ == "__main__":
    unittest.main()

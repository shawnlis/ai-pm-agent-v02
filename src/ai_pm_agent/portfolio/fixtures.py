"""Sample portfolio fixtures for tests and local experimentation."""

from __future__ import annotations

from datetime import date

from ai_pm_agent.portfolio.models import Holding, PortfolioSnapshot


def build_sample_portfolio_snapshot() -> PortfolioSnapshot:
    """Build a deterministic sample portfolio.

    Values here are fake test data only. They are not live prices, trade
    recommendations, or a representation of an actual account.
    """

    return PortfolioSnapshot(
        as_of_date=date(2026, 6, 6),
        base_currency="USD",
        cash=12_500.0,
        cash_currency="USD",
        benchmark="QQQ",
        notes="Fixture values are fake test data only.",
        holdings=[
            Holding(
                ticker="TQQQ",
                name="ProShares UltraPro QQQ",
                market="NASDAQ",
                quantity=140.0,
                cost_basis=58.0,
                current_price=72.0,
                asset_class="leveraged_etf",
                theme=["leveraged ETF", "mega-cap tech"],
                risk_bucket="leveraged_etf",
                notes="3x Nasdaq exposure fixture.",
            ),
            Holding(
                ticker="SOXL",
                name="Direxion Daily Semiconductor Bull 3X Shares",
                market="NYSEARCA",
                quantity=180.0,
                cost_basis=35.0,
                current_price=44.0,
                asset_class="leveraged_etf",
                theme=["leveraged ETF", "semiconductor", "AI infrastructure"],
                risk_bucket="leveraged_etf",
                notes="3x semiconductor exposure fixture.",
            ),
            Holding(
                ticker="NVDA",
                name="NVIDIA",
                market="NASDAQ",
                quantity=70.0,
                cost_basis=105.0,
                current_price=130.0,
                asset_class="equity",
                theme=["AI infrastructure", "semiconductor"],
                risk_bucket="single_name_growth",
            ),
            Holding(
                ticker="7709.HK",
                name="SK Hynix proxy / HY9H / 7709.HK",
                market="HKEX",
                currency="HKD",
                quantity=500.0,
                cost_basis=80.0,
                current_price=92.0,
                asset_class="equity",
                theme=["HBM", "semiconductor", "AI infrastructure"],
                risk_bucket="semiconductor_cycle",
            ),
            Holding(
                ticker="MU",
                name="Micron Technology",
                market="NASDAQ",
                quantity=55.0,
                cost_basis=98.0,
                current_price=118.0,
                asset_class="equity",
                theme=["HBM", "semiconductor"],
                risk_bucket="semiconductor_cycle",
            ),
            Holding(
                ticker="GOOGL",
                name="Alphabet",
                market="NASDAQ",
                quantity=35.0,
                cost_basis=160.0,
                current_price=185.0,
                asset_class="equity",
                theme=["cloud AI", "mega-cap tech"],
                risk_bucket="mega_cap_quality",
            ),
            Holding(
                ticker="MSFT",
                name="Microsoft",
                market="NASDAQ",
                quantity=22.0,
                cost_basis=405.0,
                current_price=470.0,
                asset_class="equity",
                theme=["cloud AI", "mega-cap tech", "AI infrastructure"],
                risk_bucket="mega_cap_quality",
            ),
            Holding(
                ticker="TSLA",
                name="Tesla",
                market="NASDAQ",
                quantity=28.0,
                cost_basis=210.0,
                current_price=245.0,
                asset_class="equity",
                theme=["EV / autonomy", "mega-cap tech"],
                risk_bucket="high_beta",
            ),
            Holding(
                ticker="ETHA",
                name="iShares Ethereum Trust ETF",
                market="NASDAQ",
                quantity=120.0,
                cost_basis=24.0,
                current_price=31.0,
                asset_class="crypto_etf",
                theme=["crypto beta"],
                risk_bucket="crypto_beta",
                notes="Crypto beta fixture, not AI equity exposure.",
            ),
        ],
    )

"""Simple offline stress scenarios for Portfolio Risk Cockpit v0.5.0."""

from __future__ import annotations

from ai_pm_agent.portfolio_risk_cockpit.exposure import calculate_totals
from ai_pm_agent.portfolio_risk_cockpit.models import NEEDS_REVIEW, REVIEW_OK, PortfolioRiskPosition


SCENARIOS = [
    {
        "scenario": "Nasdaq -10%",
        "shock_pct": -0.10,
        "notes": "Applies to Nasdaq, mega-cap technology, AI infrastructure, and leveraged ETF tagged rows.",
    },
    {
        "scenario": "Semis -15%",
        "shock_pct": -0.15,
        "notes": "Applies to semiconductor tagged rows and common semiconductor tickers.",
    },
    {
        "scenario": "USD/SGD -5%",
        "shock_pct": -0.05,
        "notes": "Applies to SGD currency rows as a simple local FX sensitivity placeholder.",
    },
    {
        "scenario": "ETH/BTC -20%",
        "shock_pct": -0.20,
        "notes": "Applies to crypto, ETH, and BTC tagged rows.",
    },
]


def calculate_stress_scenarios(positions: list[PortfolioRiskPosition]) -> list[dict[str, object]]:
    total_gross_market_value = calculate_totals(positions)["gross_market_value"]
    rows: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        matched = [position for position in positions if _matches_scenario(position, str(scenario["scenario"]))]
        impacted_exposure = sum(position.leverage_adjusted_exposure for position in matched)
        estimated_impact_value = impacted_exposure * float(scenario["shock_pct"])
        warning_codes = sorted({code for position in matched for code in position.warning_codes})
        review_status = NEEDS_REVIEW if any(position.is_needs_review for position in matched) else REVIEW_OK
        rows.append(
            {
                "scenario": scenario["scenario"],
                "shock_pct": scenario["shock_pct"],
                "impacted_tickers": ";".join(position.ticker for position in matched),
                "impacted_exposure": round(impacted_exposure, 6),
                "estimated_impact_value": round(estimated_impact_value, 6),
                "estimated_impact_pct_of_gross_market_value": _ratio(
                    estimated_impact_value,
                    total_gross_market_value,
                ),
                "review_status": review_status,
                "warning_codes": ";".join(warning_codes),
                "notes": scenario["notes"],
            }
        )
    return rows


def _matches_scenario(position: PortfolioRiskPosition, scenario: str) -> bool:
    themes = " ".join(position.themes).lower()
    ticker = position.ticker.upper()
    underlying = (position.underlying_ticker or "").upper()
    instrument_type = position.instrument_type.lower()

    if scenario == "Nasdaq -10%":
        return (
            "nasdaq" in themes
            or "mega-cap tech" in themes
            or "ai infrastructure" in themes
            or instrument_type == "leveraged_etf"
            or ticker in {"QQQ", "TQQQ", "MSFT", "GOOGL", "NVDA", "AMD", "AVGO"}
        )
    if scenario == "Semis -15%":
        return "semi" in themes or ticker in {"MU", "NVDA", "AMD", "AVGO", "SOXL"} or underlying in {
            "MU",
            "NVDA",
            "AMD",
            "AVGO",
            "SOXL",
        }
    if scenario == "USD/SGD -5%":
        return position.currency.upper() == "SGD"
    if scenario == "ETH/BTC -20%":
        return "crypto" in themes or ticker.startswith(("ETH", "BTC")) or underlying.startswith(("ETH", "BTC"))
    return False


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 10)

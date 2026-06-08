"""Portfolio data models.

The models in this module are intentionally independent from the main
research runner so they can be adopted incrementally by reporting, sizing,
and risk modules.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


LEVERAGED_ETF_DEFAULTS = {"TQQQ": 3.0, "SOXL": 3.0}
ETHA_DEFAULT_ASSET_CLASS = "crypto_etf"
ETHA_DEFAULT_THEME = "crypto beta"
ETHA_DEFAULT_RISK_BUCKET = "crypto_beta"


def _normalize_ticker(value: str) -> str:
    return value.strip().upper()


class Holding(BaseModel):
    """A single portfolio holding with optional valuation data."""

    model_config = ConfigDict(validate_assignment=True)

    ticker: str
    name: str | None = None
    market: str | None = None
    currency: str = "USD"
    asset_class: str = "equity"
    quantity: float
    cost_basis: float | None = None
    current_price: float | None = None
    market_value: float | None = None
    theme: list[str] = Field(default_factory=list)
    risk_bucket: str | None = None
    leverage_multiplier: float = 1.0
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_security_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        ticker = _normalize_ticker(str(values.get("ticker", "")))

        if ticker in LEVERAGED_ETF_DEFAULTS and values.get("leverage_multiplier") is None:
            values["leverage_multiplier"] = LEVERAGED_ETF_DEFAULTS[ticker]

        if ticker == "ETHA":
            asset_class = values.get("asset_class")
            if asset_class is None or str(asset_class).strip().lower() in {"", "equity", "stock", "ai equity"}:
                values["asset_class"] = ETHA_DEFAULT_ASSET_CLASS

            themes = list(values.get("theme") or [])
            theme_keys = {str(theme).strip().lower() for theme in themes}
            if ETHA_DEFAULT_THEME not in theme_keys:
                themes.append(ETHA_DEFAULT_THEME)
            values["theme"] = themes

            if not values.get("risk_bucket"):
                values["risk_bucket"] = ETHA_DEFAULT_RISK_BUCKET

        return values

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = _normalize_ticker(value)
        if not ticker:
            raise ValueError("ticker must not be blank")
        return ticker

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if not currency:
            raise ValueError("currency must not be blank")
        return currency

    @field_validator("asset_class")
    @classmethod
    def normalize_asset_class(cls, value: str) -> str:
        asset_class = value.strip()
        if not asset_class:
            raise ValueError("asset_class must not be blank")
        return asset_class

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: list[str]) -> list[str]:
        return [theme.strip() for theme in value if theme and theme.strip()]

    @field_validator("leverage_multiplier")
    @classmethod
    def validate_leverage_multiplier(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("leverage_multiplier must be greater than zero")
        return value

    @model_validator(mode="after")
    def fill_market_value_from_price(self) -> "Holding":
        if self.market_value is None and self.current_price is not None:
            self.market_value = self.quantity * self.current_price
        return self

    @property
    def valuation_complete(self) -> bool:
        return self.market_value is not None


class PortfolioSnapshot(BaseModel):
    """A point-in-time view of holdings plus cash."""

    model_config = ConfigDict(validate_assignment=True)

    as_of_date: date
    base_currency: str = "USD"
    holdings: list[Holding] = Field(default_factory=list)
    cash: float = 0.0
    cash_currency: str = "USD"
    benchmark: str | None = None
    notes: str | None = None

    @field_validator("base_currency", "cash_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.strip().upper()
        if not currency:
            raise ValueError("currency must not be blank")
        return currency

    @property
    def total_market_value(self) -> float:
        return sum(holding.market_value or 0.0 for holding in self.holdings)

    @property
    def total_cash(self) -> float:
        return self.cash

    @property
    def total_equity_value(self) -> float:
        return self.total_market_value + self.total_cash

    @property
    def gross_exposure(self) -> float:
        denominator = self.total_equity_value
        if denominator == 0:
            return 0.0
        return sum(abs(holding.market_value or 0.0) for holding in self.holdings) / denominator

    @property
    def leverage_adjusted_exposure(self) -> float:
        denominator = self.total_equity_value
        if denominator == 0:
            return 0.0
        adjusted_value = sum(
            abs(holding.market_value or 0.0) * holding.leverage_multiplier for holding in self.holdings
        )
        return adjusted_value / denominator

    @property
    def holding_weights(self) -> dict[str, float]:
        denominator = self.total_equity_value
        if denominator == 0:
            return {holding.ticker: 0.0 for holding in self.holdings}
        return {holding.ticker: (holding.market_value or 0.0) / denominator for holding in self.holdings}

    @property
    def theme_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: holding.theme)

    @property
    def asset_class_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.asset_class])

    @property
    def currency_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.currency])

    @property
    def risk_bucket_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.risk_bucket] if holding.risk_bucket else [])

    @property
    def incomplete_valuation_holdings(self) -> list[str]:
        return [holding.ticker for holding in self.holdings if not holding.valuation_complete]


def _bucket_exposure(snapshot: PortfolioSnapshot, bucket_getter: Any) -> dict[str, float]:
    denominator = snapshot.total_equity_value
    exposure: dict[str, float] = {}
    if denominator == 0:
        return exposure

    for holding in snapshot.holdings:
        market_value = holding.market_value
        if market_value is None:
            continue
        for bucket in bucket_getter(holding):
            if not bucket:
                continue
            exposure[str(bucket)] = exposure.get(str(bucket), 0.0) + market_value / denominator
    return exposure

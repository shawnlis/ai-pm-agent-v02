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


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class LookThroughComponent(BaseModel):
    """A manually supplied look-through component for a holding.

    This is intentionally local-only metadata. The model does not fetch ETF
    constituents, index weights, prices, FX rates, or any external data.
    """

    model_config = ConfigDict(validate_assignment=True)

    holding_ticker: str | None = None
    component_issuer_name: str | None = None
    component_issuer_canonical_id: str | None = None
    component_ticker: str | None = None
    component_weight: float
    sector: str | None = None
    industry: str | None = None
    country_of_risk: str | None = None
    region: str | None = None
    theme: list[str] = Field(default_factory=list)
    instrument_type: str | None = None
    source_note: str | None = None

    @field_validator("holding_ticker", "component_ticker")
    @classmethod
    def normalize_optional_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ticker = _normalize_ticker(value)
        return ticker or None

    @field_validator(
        "component_issuer_name",
        "component_issuer_canonical_id",
        "sector",
        "industry",
        "country_of_risk",
        "region",
        "instrument_type",
        "source_note",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_string(value)

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: list[str]) -> list[str]:
        return [theme.strip() for theme in value if theme and theme.strip()]

    @field_validator("component_weight")
    @classmethod
    def validate_component_weight(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("component_weight must be between 0 and 1")
        return value


class Holding(BaseModel):
    """A single portfolio holding with optional valuation data."""

    model_config = ConfigDict(validate_assignment=True)

    ticker: str
    name: str | None = None
    market: str | None = None
    currency: str = "USD"
    asset_class: str = "equity"
    instrument_type: str | None = None
    quantity: float
    cost_basis: float | None = None
    current_price: float | None = None
    market_value: float | None = None
    theme: list[str] = Field(default_factory=list)
    risk_bucket: str | None = None
    leverage_multiplier: float = 1.0
    issuer_name: str | None = None
    issuer_canonical_id: str | None = None
    underlying_issuer_name: str | None = None
    underlying_ticker: str | None = None
    listing_country: str | None = None
    country_of_risk: str | None = None
    region: str | None = None
    sector: str | None = None
    industry: str | None = None
    trading_currency: str | None = None
    base_currency: str | None = None
    fx_rate_to_base: float | None = None
    market_value_local: float | None = None
    market_value_base: float | None = None
    leverage_factor: float | None = None
    lookthrough_available: bool = False
    lookthrough_source: str | None = None
    lookthrough_components: list[LookThroughComponent] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_security_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        ticker = _normalize_ticker(str(values.get("ticker", "")))

        if "themes" in values and "theme" not in values:
            values["theme"] = values["themes"]

        if values.get("trading_currency") is not None and values.get("currency") is None:
            values["currency"] = values["trading_currency"]

        if values.get("leverage_factor") is not None and values.get("leverage_multiplier") is None:
            values["leverage_multiplier"] = values["leverage_factor"]

        if ticker in LEVERAGED_ETF_DEFAULTS and values.get("leverage_multiplier") is None:
            values["leverage_multiplier"] = LEVERAGED_ETF_DEFAULTS[ticker]

        if ticker in LEVERAGED_ETF_DEFAULTS and not values.get("instrument_type"):
            values["instrument_type"] = "leveraged_etf"

        if ticker == "ETHA":
            asset_class = values.get("asset_class")
            if asset_class is None or str(asset_class).strip().lower() in {"", "equity", "stock", "ai equity"}:
                values["asset_class"] = ETHA_DEFAULT_ASSET_CLASS

            if not values.get("instrument_type"):
                values["instrument_type"] = ETHA_DEFAULT_ASSET_CLASS

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

    @field_validator("trading_currency", "base_currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        currency = value.strip().upper()
        return currency or None

    @field_validator("underlying_ticker")
    @classmethod
    def normalize_underlying_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ticker = _normalize_ticker(value)
        return ticker or None

    @field_validator(
        "instrument_type",
        "issuer_name",
        "issuer_canonical_id",
        "underlying_issuer_name",
        "listing_country",
        "country_of_risk",
        "region",
        "sector",
        "industry",
        "lookthrough_source",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_string(value)

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

    @field_validator("leverage_factor")
    @classmethod
    def validate_leverage_factor(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("leverage_factor must be greater than zero")
        return value

    @field_validator("fx_rate_to_base")
    @classmethod
    def validate_fx_rate_to_base(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("fx_rate_to_base must be greater than zero")
        return value

    @model_validator(mode="after")
    def fill_market_value_from_price(self) -> "Holding":
        if self.market_value is None and self.market_value_local is not None:
            object.__setattr__(self, "market_value", self.market_value_local)
        if self.market_value is None and self.current_price is not None:
            object.__setattr__(self, "market_value", self.quantity * self.current_price)
        if self.market_value_local is None and self.market_value is not None:
            object.__setattr__(self, "market_value_local", self.market_value)
        if self.market_value_base is None and self.market_value_local is not None and self.fx_rate_to_base is not None:
            object.__setattr__(self, "market_value_base", self.market_value_local * self.fx_rate_to_base)
        if self.trading_currency is None:
            object.__setattr__(self, "trading_currency", self.currency)
        if self.leverage_factor is None:
            object.__setattr__(self, "leverage_factor", self.leverage_multiplier)
        if self.lookthrough_components:
            object.__setattr__(self, "lookthrough_available", True)
        return self

    @property
    def themes(self) -> list[str]:
        return self.theme

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
    def total_base_market_value(self) -> float:
        return sum(_holding_base_market_value(holding) or 0.0 for holding in self.holdings)

    @property
    def total_cash(self) -> float:
        return self.cash

    @property
    def total_equity_value(self) -> float:
        return self.total_market_value + self.total_cash

    @property
    def total_base_equity_value(self) -> float:
        return self.total_base_market_value + self.total_cash

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
    def sector_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.sector] if holding.sector else [], use_base_value=True)

    @property
    def industry_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.industry] if holding.industry else [], use_base_value=True)

    @property
    def region_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [holding.region] if holding.region else [], use_base_value=True)

    @property
    def country_of_risk_exposure(self) -> dict[str, float]:
        return _bucket_exposure(
            self,
            lambda holding: [holding.country_of_risk] if holding.country_of_risk else [],
            use_base_value=True,
        )

    @property
    def issuer_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [_issuer_key(holding)], use_base_value=True)

    @property
    def instrument_type_exposure(self) -> dict[str, float]:
        return _bucket_exposure(self, lambda holding: [_instrument_type(holding)], use_base_value=True)

    @property
    def base_market_value_weights(self) -> dict[str, float]:
        denominator = self.total_base_equity_value
        if denominator == 0:
            return {holding.ticker: 0.0 for holding in self.holdings}
        return {
            ticker: weight
            for ticker, weight in sorted(
                (
                    (holding.ticker, (_holding_base_market_value(holding) or 0.0) / denominator)
                    for holding in self.holdings
                ),
                key=lambda item: item[0],
            )
        }

    @property
    def incomplete_valuation_holdings(self) -> list[str]:
        return [holding.ticker for holding in self.holdings if not holding.valuation_complete]


def _holding_base_market_value(holding: Holding) -> float | None:
    if holding.market_value_base is not None:
        return holding.market_value_base
    if holding.market_value_local is not None and holding.fx_rate_to_base is not None:
        return holding.market_value_local * holding.fx_rate_to_base
    return holding.market_value


def _issuer_key(holding: Holding) -> str:
    return (
        holding.issuer_canonical_id
        or holding.issuer_name
        or holding.underlying_issuer_name
        or holding.underlying_ticker
        or holding.ticker
    )


def _instrument_type(holding: Holding) -> str:
    return holding.instrument_type or holding.asset_class


def _bucket_exposure(
    snapshot: PortfolioSnapshot,
    bucket_getter: Any,
    *,
    use_base_value: bool = False,
) -> dict[str, float]:
    denominator = snapshot.total_base_equity_value if use_base_value else snapshot.total_equity_value
    exposure: dict[str, float] = {}
    if denominator == 0:
        return exposure

    for holding in snapshot.holdings:
        market_value = _holding_base_market_value(holding) if use_base_value else holding.market_value
        if market_value is None:
            continue
        for bucket in bucket_getter(holding):
            if not bucket:
                continue
            exposure[str(bucket)] = exposure.get(str(bucket), 0.0) + market_value / denominator
    return dict(sorted(exposure.items()))

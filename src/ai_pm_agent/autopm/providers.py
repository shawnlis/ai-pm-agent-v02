"""Fixture-only autopm data providers.

These providers read explicit local CSV/JSON fixture files. They do not use
network calls, live providers, broker adapters, portfolio account connections,
or execution systems.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
import json
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from ai_pm_agent.autopm.data_contracts import EstimateSnapshot, FundamentalSnapshot, MarketSnapshot
from ai_pm_agent.autopm.models import DataProviderLevel


T = TypeVar("T")

BASE_REQUIRED_COLUMNS = {
    "ticker",
    "as_of_date",
    "source_ids",
    "reliability",
    "fixture_only",
}
STALE_AFTER_DAYS = 30


class FixtureProviderError(ValueError):
    """Raised when fixture provider input fails closed."""


class _BaseFixtureProvider(Generic[T]):
    provider_name = "fixture"
    provider_level = DataProviderLevel.LEVEL_0_FIXTURE
    required_columns: set[str] = set()

    def __init__(self, path: str | Path, *, stale_after_days: int = STALE_AFTER_DAYS) -> None:
        self.path = Path(path)
        self.stale_after_days = stale_after_days

    def load(self) -> list[T]:
        rows = self._read_rows()
        self._validate_columns(rows)
        retrieval_time = datetime.now(UTC).replace(microsecond=0).isoformat()
        return [self._build_snapshot(row, retrieval_time) for row in rows]

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists() or not self.path.is_file():
            raise FixtureProviderError(f"fixture file not found: {self.path}")
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        if suffix == ".json":
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                rows = payload.get("rows")
            else:
                rows = payload
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise FixtureProviderError("fixture JSON must be a list of objects or {'rows': [...]}")
            return [dict(row) for row in rows]
        raise FixtureProviderError("fixture provider supports only .csv and .json files")

    def _validate_columns(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise FixtureProviderError("fixture file contains no rows")
        columns = set().union(*(row.keys() for row in rows))
        required = BASE_REQUIRED_COLUMNS | self.required_columns
        missing = sorted(required - columns)
        if missing:
            raise FixtureProviderError(f"missing required fixture columns: {', '.join(missing)}")

    def _metadata(self, row: dict[str, Any], retrieval_time: str) -> dict[str, Any]:
        provider_level_text = _text(row.get("provider_level"))
        if provider_level_text and provider_level_text != DataProviderLevel.LEVEL_0_FIXTURE.value:
            raise FixtureProviderError("fixture providers only accept LEVEL_0_FIXTURE rows")
        if not _bool(row.get("fixture_only")):
            raise FixtureProviderError("fixture providers reject non-fixture rows")

        as_of_date = _text(row.get("as_of_date"))
        source_ids = _tuple_text(row.get("source_ids"))
        if not source_ids:
            raise FixtureProviderError("fixture row must include at least one source_id")

        warning_codes = list(_tuple_text(row.get("warning_codes")))
        stale = _bool(row.get("stale")) or _is_stale(as_of_date, self.stale_after_days)
        if stale and "STALE_DATA" not in warning_codes:
            warning_codes.append("STALE_DATA")

        return {
            "ticker": _required_text(row, "ticker"),
            "provider_name": _text(row.get("provider_name")) or self.provider_name,
            "provider_level": self.provider_level,
            "retrieval_time": retrieval_time,
            "as_of_date": as_of_date,
            "source_ids": source_ids,
            "reliability": _float(row.get("reliability"), "reliability"),
            "stale": stale,
            "warning_codes": tuple(warning_codes),
            "fixture_only": True,
        }

    def _build_snapshot(self, row: dict[str, Any], retrieval_time: str) -> T:
        raise NotImplementedError


class FixtureMarketDataProvider(_BaseFixtureProvider[MarketSnapshot]):
    required_columns = {"price", "currency"}

    def _build_snapshot(self, row: dict[str, Any], retrieval_time: str) -> MarketSnapshot:
        return MarketSnapshot(
            **self._metadata(row, retrieval_time),
            price=_float(row.get("price"), "price"),
            currency=_required_text(row, "currency"),
            volume=_optional_float(row.get("volume")),
        )


class FixtureFundamentalDataProvider(_BaseFixtureProvider[FundamentalSnapshot]):
    required_columns = {"revenue", "gross_margin_pct", "fcf_margin_pct"}

    def _build_snapshot(self, row: dict[str, Any], retrieval_time: str) -> FundamentalSnapshot:
        return FundamentalSnapshot(
            **self._metadata(row, retrieval_time),
            revenue=_optional_float(row.get("revenue")),
            gross_margin_pct=_optional_float(row.get("gross_margin_pct")),
            fcf_margin_pct=_optional_float(row.get("fcf_margin_pct")),
            debt_to_equity=_optional_float(row.get("debt_to_equity")),
        )


class FixtureEstimateDataProvider(_BaseFixtureProvider[EstimateSnapshot]):
    required_columns = {"next_eps", "eps_revision_pct"}

    def _build_snapshot(self, row: dict[str, Any], retrieval_time: str) -> EstimateSnapshot:
        return EstimateSnapshot(
            **self._metadata(row, retrieval_time),
            next_eps=_optional_float(row.get("next_eps")),
            eps_revision_pct=_optional_float(row.get("eps_revision_pct")),
            revenue_revision_pct=_optional_float(row.get("revenue_revision_pct")),
        )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text(row.get(key))
    if not value:
        raise FixtureProviderError(f"required fixture value missing: {key}")
    return value


def _float(value: Any, key: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FixtureProviderError(f"invalid numeric fixture value: {key}") from exc


def _optional_float(value: Any) -> float | None:
    if _text(value) == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FixtureProviderError("invalid optional numeric fixture value") from exc


def _tuple_text(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(_text(item) for item in value if _text(item))
    return tuple(part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip())


def _bool(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _is_stale(as_of_date: str, stale_after_days: int) -> bool:
    try:
        parsed = date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise FixtureProviderError("as_of_date must use YYYY-MM-DD") from exc
    return (datetime.now(UTC).date() - parsed).days > stale_after_days

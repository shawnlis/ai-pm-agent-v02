from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import shutil
import socket
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.data_contracts import EstimateSnapshot, FundamentalSnapshot, MarketSnapshot
from ai_pm_agent.autopm.models import DataProviderLevel
from ai_pm_agent.autopm.providers import (
    FixtureEstimateDataProvider,
    FixtureFundamentalDataProvider,
    FixtureMarketDataProvider,
    FixtureProviderError,
)


REVIEW_FIRST_DIRS = (
    "evidence_db",
    "thesis_gap_monitor",
    "opportunity_discovery",
    "ai_infra_pipeline",
    "portfolio_risk_cockpit",
    "short_put_risk_monitor",
    "risk_cockpit_pipeline",
    "approval",
)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    temp_root = Path(".pytest_autopm_provider_tmp")
    path = temp_root / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_fixture_market_provider_loads_csv_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "market.csv"
    _write_csv(
        path,
        [
            "ticker",
            "as_of_date",
            "source_ids",
            "reliability",
            "fixture_only",
            "price",
            "currency",
            "volume",
        ],
        [["TEST", "2099-01-01", "fixture:test", "0.95", "true", "123.45", "USD", "1000"]],
    )

    snapshots = FixtureMarketDataProvider(path).load()

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.ticker == "TEST"
    assert snapshot.provider_name == "fixture"
    assert snapshot.provider_level == DataProviderLevel.LEVEL_0_FIXTURE
    assert snapshot.retrieval_time
    assert snapshot.as_of_date == "2099-01-01"
    assert snapshot.source_ids == ("fixture:test",)
    assert snapshot.reliability == 0.95
    assert snapshot.stale is False
    assert snapshot.warning_codes == ()
    assert snapshot.fixture_only is True
    assert snapshot.price == 123.45
    assert snapshot.currency == "USD"


def test_fixture_fundamental_provider_loads_json_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "fundamentals.json"
    path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "ticker": "TEST",
                        "as_of_date": "2099-01-01",
                        "source_ids": ["fixture:fundamental"],
                        "reliability": 0.9,
                        "fixture_only": True,
                        "revenue": 1000,
                        "gross_margin_pct": 45.0,
                        "fcf_margin_pct": 12.0,
                        "debt_to_equity": 0.2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshots = FixtureFundamentalDataProvider(path).load()

    assert len(snapshots) == 1
    assert isinstance(snapshots[0], FundamentalSnapshot)
    assert snapshots[0].source_ids == ("fixture:fundamental",)
    assert snapshots[0].gross_margin_pct == 45.0


def test_fixture_estimate_provider_loads_json_list(tmp_path: Path) -> None:
    path = tmp_path / "estimates.json"
    path.write_text(
        json.dumps(
            [
                {
                    "ticker": "TEST",
                    "as_of_date": "2099-01-01",
                    "source_ids": "fixture:estimate",
                    "reliability": "0.8",
                    "fixture_only": "true",
                    "next_eps": "5.5",
                    "eps_revision_pct": "3.0",
                    "revenue_revision_pct": "1.5",
                }
            ]
        ),
        encoding="utf-8",
    )

    snapshots = FixtureEstimateDataProvider(path).load()

    assert len(snapshots) == 1
    assert isinstance(snapshots[0], EstimateSnapshot)
    assert snapshots[0].eps_revision_pct == 3.0


def test_missing_required_provider_columns_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "market.csv"
    _write_csv(path, ["ticker", "as_of_date", "fixture_only", "price"], [["TEST", "2099-01-01", "true", "1"]])

    with pytest.raises(FixtureProviderError, match="missing required fixture columns"):
        FixtureMarketDataProvider(path).load()


def test_stale_data_warning_emitted(tmp_path: Path) -> None:
    path = tmp_path / "market.csv"
    _write_csv(
        path,
        ["ticker", "as_of_date", "source_ids", "reliability", "fixture_only", "price", "currency"],
        [["OLD", "2000-01-01", "fixture:old", "0.9", "true", "10", "USD"]],
    )

    snapshot = FixtureMarketDataProvider(path).load()[0]

    assert snapshot.stale is True
    assert "STALE_DATA" in snapshot.warning_codes


def test_non_fixture_provider_row_rejected(tmp_path: Path) -> None:
    path = tmp_path / "market.csv"
    _write_csv(
        path,
        [
            "ticker",
            "as_of_date",
            "source_ids",
            "reliability",
            "fixture_only",
            "provider_level",
            "price",
            "currency",
        ],
        [["LIVE", "2099-01-01", "live:bad", "0.9", "false", "LEVEL_2_MARKET_DATA_VENDOR", "10", "USD"]],
    )

    with pytest.raises(FixtureProviderError):
        FixtureMarketDataProvider(path).load()


def test_provider_metadata_present(tmp_path: Path) -> None:
    path = tmp_path / "market.csv"
    _write_csv(
        path,
        ["ticker", "as_of_date", "source_ids", "reliability", "fixture_only", "price", "currency"],
        [["META", "2099-01-01", "fixture:meta", "1.0", "true", "10", "USD"]],
    )

    snapshot = FixtureMarketDataProvider(path).load()[0]

    assert snapshot.provider_name
    assert snapshot.provider_level == DataProviderLevel.LEVEL_0_FIXTURE
    assert snapshot.retrieval_time
    assert snapshot.as_of_date
    assert snapshot.source_ids
    assert snapshot.reliability == 1.0
    assert snapshot.fixture_only is True


def test_fixture_provider_performs_no_network_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "market.csv"
    _write_csv(
        path,
        ["ticker", "as_of_date", "source_ids", "reliability", "fixture_only", "price", "currency"],
        [["NET", "2099-01-01", "fixture:net", "0.7", "true", "10", "USD"]],
    )

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert FixtureMarketDataProvider(path).load()[0].ticker == "NET"


def test_no_autopm_module_imports_broker_or_execution_modules() -> None:
    autopm_root = Path("src/ai_pm_agent/autopm")
    forbidden_import_terms = ("broker", "ibkr", "execution")
    offenders: list[str] = []

    for path in autopm_root.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in forbidden_import_terms):
                offenders.append(f"{path}:{line}")

    assert offenders == []


def test_review_first_modules_do_not_import_autopm() -> None:
    offenders: list[str] = []
    root = Path("src/ai_pm_agent")

    for folder in REVIEW_FIRST_DIRS:
        for path in (root / folder).rglob("*.py"):
            if "ai_pm_agent.autopm" in path.read_text(encoding="utf-8"):
                offenders.append(str(path))

    assert offenders == []

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.portfolio.runner import PortfolioRunnerError, run_from_paths


HOLDINGS_FIELDS = [
    "portfolio_id",
    "as_of_date",
    "ticker",
    "name",
    "quantity",
    "market_value_local",
    "trading_currency",
    "base_currency",
    "fx_rate_to_base",
    "market_value_base",
    "instrument_type",
    "issuer_name",
    "issuer_canonical_id",
    "underlying_issuer_name",
    "underlying_ticker",
    "listing_country",
    "country_of_risk",
    "region",
    "sector",
    "industry",
    "themes",
    "leverage_factor",
    "notes",
]


class PortfolioRunnerTests(unittest.TestCase):
    def test_valid_holdings_csv_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = tmp_path / "holdings.csv"
            _write_csv(
                holdings,
                HOLDINGS_FIELDS,
                [
                    _holding_row(
                        ticker="MSFT",
                        name="Microsoft",
                        market_value_base="1000",
                        instrument_type="stock",
                        issuer_canonical_id="MICROSOFT",
                        sector="Information Technology",
                        industry="Software",
                        themes="cloud AI;mega-cap tech",
                    ),
                    _holding_row(
                        ticker="ETHA",
                        name="iShares Ethereum Trust ETF",
                        market_value_base="500",
                        instrument_type="crypto_etf",
                        issuer_canonical_id="ISHARES",
                        sector="Digital Assets",
                        industry="Crypto asset ETF",
                        region="Global",
                        country_of_risk="Global",
                        themes="crypto beta",
                    ),
                ],
            )

            report = tmp_path / "report.md"
            summary = tmp_path / "summary.json"
            result = run_from_paths(holdings_path=holdings, out_path=report, json_out_path=summary)

            self.assertTrue(report.exists())
            self.assertTrue(summary.exists())
            self.assertEqual(result.snapshot.total_base_equity_value, 1500.0)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["portfolio_id"], "test_portfolio")
            self.assertEqual(payload["counts"]["holdings"], 2)
            self.assertIn("sector", payload["exposures"])

    def test_missing_optional_mapping_file_warns_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = _write_minimal_holdings(tmp_path)

            result = run_from_paths(
                holdings_path=holdings,
                issuer_mapping_path=tmp_path / "missing_issuer_mapping.csv",
                out_path=tmp_path / "report.md",
            )

            self.assertTrue(any("optional issuer mapping file not found" in warning for warning in result.warnings))
            self.assertTrue((tmp_path / "report.md").exists())

    def test_missing_required_holdings_column_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            _write_csv(path, ["portfolio_id", "as_of_date", "quantity"], [{"portfolio_id": "x", "as_of_date": "2026-06-08", "quantity": "1"}])

            with self.assertRaisesRegex(PortfolioRunnerError, "missing required columns: ticker"):
                run_from_paths(holdings_path=path, out_path=Path(tmp) / "report.md")

    def test_invalid_numeric_value_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            row = _holding_row(ticker="NVDA", market_value_base="1000")
            row["quantity"] = "not-a-number"
            _write_csv(path, HOLDINGS_FIELDS, [row])

            with self.assertRaisesRegex(PortfolioRunnerError, "invalid numeric value for quantity"):
                run_from_paths(holdings_path=path, out_path=Path(tmp) / "report.md")

    def test_fx_snapshot_application(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = tmp_path / "holdings.csv"
            _write_csv(
                holdings,
                HOLDINGS_FIELDS,
                [
                    _holding_row(
                        ticker="7709.HK",
                        market_value_local="1000",
                        trading_currency="HKD",
                        base_currency="USD",
                        market_value_base="",
                        fx_rate_to_base="",
                        issuer_canonical_id="SK_HYNIX",
                        sector="Information Technology",
                        industry="Semiconductors",
                        region="Asia",
                        country_of_risk="South Korea",
                    )
                ],
            )
            fx = tmp_path / "fx.csv"
            _write_csv(
                fx,
                ["currency", "base_currency", "fx_rate_to_base", "as_of_date", "source_note"],
                [{"currency": "HKD", "base_currency": "USD", "fx_rate_to_base": "0.125", "as_of_date": "2026-06-08", "source_note": "test"}],
            )

            result = run_from_paths(holdings_path=holdings, fx_snapshot_path=fx, out_path=tmp_path / "report.md")

            self.assertEqual(result.snapshot.holdings[0].market_value_base, 125.0)
            self.assertFalse(any("missing FX" in warning for warning in result.warnings))

    def test_issuer_and_taxonomy_mapping_application(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = tmp_path / "holdings.csv"
            _write_csv(holdings, HOLDINGS_FIELDS, [_holding_row(ticker="HY9H", issuer_canonical_id="", sector="", industry="", region="", country_of_risk="", themes="")])
            issuer_mapping = tmp_path / "issuer.csv"
            _write_csv(
                issuer_mapping,
                ["ticker", "issuer_name", "issuer_canonical_id", "underlying_issuer_name", "underlying_ticker", "listing_country", "country_of_risk", "region"],
                [
                    {
                        "ticker": "HY9H",
                        "issuer_name": "SK Hynix",
                        "issuer_canonical_id": "SK_HYNIX",
                        "underlying_issuer_name": "SK Hynix",
                        "underlying_ticker": "000660.KS",
                        "listing_country": "Germany",
                        "country_of_risk": "South Korea",
                        "region": "Asia",
                    }
                ],
            )
            taxonomy_mapping = tmp_path / "taxonomy.csv"
            _write_csv(
                taxonomy_mapping,
                ["ticker", "sector", "industry", "region", "country_of_risk", "themes"],
                [
                    {
                        "ticker": "HY9H",
                        "sector": "Information Technology",
                        "industry": "Semiconductors",
                        "region": "Asia",
                        "country_of_risk": "South Korea",
                        "themes": "HBM;semiconductor",
                    }
                ],
            )

            result = run_from_paths(
                holdings_path=holdings,
                issuer_mapping_path=issuer_mapping,
                taxonomy_mapping_path=taxonomy_mapping,
                out_path=tmp_path / "report.md",
            )

            holding = result.snapshot.holdings[0]
            self.assertEqual(holding.issuer_canonical_id, "SK_HYNIX")
            self.assertEqual(holding.sector, "Information Technology")
            self.assertEqual(holding.theme, ["HBM", "semiconductor"])

    def test_manual_lookthrough_application_and_weight_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = _write_minimal_holdings(tmp_path, ticker="SOXL")
            lookthrough = tmp_path / "lookthrough.csv"
            _write_csv(
                lookthrough,
                [
                    "parent_ticker",
                    "component_issuer_name",
                    "component_issuer_canonical_id",
                    "component_ticker",
                    "component_weight",
                    "sector",
                    "industry",
                    "country_of_risk",
                    "region",
                    "themes",
                    "source_note",
                ],
                [
                    {
                        "parent_ticker": "SOXL",
                        "component_issuer_name": "NVIDIA",
                        "component_issuer_canonical_id": "NVIDIA",
                        "component_ticker": "NVDA",
                        "component_weight": "0.6",
                        "sector": "Information Technology",
                        "industry": "Semiconductors",
                        "country_of_risk": "United States",
                        "region": "North America",
                        "themes": "AI infrastructure;semiconductor",
                        "source_note": "test",
                    }
                ],
            )

            result = run_from_paths(holdings_path=holdings, manual_lookthrough_path=lookthrough, out_path=tmp_path / "report.md")

            self.assertTrue(result.snapshot.holdings[0].lookthrough_available)
            self.assertTrue(any("SOXL: manual look-through weights sum to 0.6000" in warning for warning in result.warnings))
            self.assertIn("Information Technology", result.exposures["lookthrough_sector"])

    def test_manual_lookthrough_weight_above_one_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = _write_minimal_holdings(tmp_path, ticker="TQQQ")
            lookthrough = tmp_path / "lookthrough.csv"
            _write_csv(
                lookthrough,
                ["parent_ticker", "component_weight", "sector"],
                [
                    {"parent_ticker": "TQQQ", "component_weight": "0.7", "sector": "Information Technology"},
                    {"parent_ticker": "TQQQ", "component_weight": "0.5", "sector": "Communication Services"},
                ],
            )

            result = run_from_paths(holdings_path=holdings, manual_lookthrough_path=lookthrough, out_path=tmp_path / "report.md")

            self.assertTrue(any("TQQQ: manual look-through weights sum to 1.2000" in warning for warning in result.warnings))

    def test_json_input_and_deterministic_output_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            holdings = tmp_path / "holdings.json"
            rows = [
                _holding_row(ticker="ZZZ", market_value_base="100", sector="Z Sector", issuer_canonical_id="Z_ISSUER"),
                _holding_row(ticker="AAA", market_value_base="200", sector="A Sector", issuer_canonical_id="A_ISSUER"),
            ]
            holdings.write_text(json.dumps({"rows": rows}), encoding="utf-8")
            summary = tmp_path / "summary.json"

            result = run_from_paths(holdings_path=holdings, out_path=tmp_path / "report.md", json_out_path=summary)
            payload = json.loads(summary.read_text(encoding="utf-8"))

            self.assertEqual(list(result.exposures["base_market_value"].keys()), ["AAA", "ZZZ"])
            self.assertEqual(list(payload["exposures"]["base_market_value"].keys()), ["AAA", "ZZZ"])


def _holding_row(**overrides: str) -> dict[str, str]:
    row = {
        "portfolio_id": "test_portfolio",
        "as_of_date": "2026-06-08",
        "ticker": "MSFT",
        "name": "",
        "quantity": "1",
        "market_value_local": "1000",
        "trading_currency": "USD",
        "base_currency": "USD",
        "fx_rate_to_base": "",
        "market_value_base": "1000",
        "instrument_type": "stock",
        "issuer_name": "",
        "issuer_canonical_id": "MICROSOFT",
        "underlying_issuer_name": "",
        "underlying_ticker": "",
        "listing_country": "United States",
        "country_of_risk": "United States",
        "region": "North America",
        "sector": "Information Technology",
        "industry": "Software",
        "themes": "cloud AI",
        "leverage_factor": "1.0",
        "notes": "test fixture",
    }
    row.update(overrides)
    return row


def _write_minimal_holdings(tmp_path: Path, ticker: str = "MSFT") -> Path:
    holdings = tmp_path / "holdings.csv"
    _write_csv(holdings, HOLDINGS_FIELDS, [_holding_row(ticker=ticker)])
    return holdings


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    unittest.main()

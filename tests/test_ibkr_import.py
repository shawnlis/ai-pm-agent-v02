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

from ai_pm_agent.portfolio.ibkr_import import import_ibkr_statement_files, main
from ai_pm_agent.portfolio.runner import run_from_paths


class IbkrStatementImportTests(unittest.TestCase):
    def test_plain_csv_writes_required_review_and_runner_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "ibkr.csv"
            _write_csv(
                source,
                [
                    "Asset Category",
                    "Currency",
                    "Symbol",
                    "Description",
                    "Quantity",
                    "Market Value",
                    "Market Value in Base",
                    "Security Type",
                    "Issuer",
                    "Report Date",
                ],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "MSFT",
                        "Description": "Microsoft Corp",
                        "Quantity": "35",
                        "Market Value": "16000",
                        "Market Value in Base": "16000",
                        "Security Type": "STK",
                        "Issuer": "Microsoft",
                        "Report Date": "2026-06-08",
                    },
                    {
                        "Asset Category": "Cash",
                        "Currency": "USD",
                        "Symbol": "USD Cash",
                        "Description": "US Dollar cash balance",
                        "Quantity": "5000",
                        "Market Value": "5000",
                        "Market Value in Base": "5000",
                        "Security Type": "CASH",
                        "Issuer": "",
                        "Report Date": "2026-06-08",
                    },
                ],
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                base_currency="USD",
            )

            self.assertEqual(result.as_of_date, "2026-06-08")
            self.assertEqual(len(result.review_rows), 2)
            self.assertEqual(len(result.ready_rows), 1)
            self.assertTrue((tmp_path / "out" / "parsed_holdings_review.csv").exists())
            self.assertTrue((tmp_path / "out" / "portfolio_runner_ready_holdings.csv").exists())
            self.assertTrue((tmp_path / "out" / "ibkr_import_warnings.md").exists())
            self.assertTrue((tmp_path / "out" / "ibkr_import_summary.json").exists())
            self.assertTrue(any("cash-like row not converted" in warning for warning in result.warnings))

            ready_rows = _read_csv(tmp_path / "out" / "portfolio_runner_ready_holdings.csv")
            self.assertEqual(ready_rows[0]["ticker"], "MSFT")
            self.assertEqual(ready_rows[0]["portfolio_id"], "test_ibkr")
            self.assertIn("IBKR_IMPORT_REVIEW_REQUIRED", ready_rows[0]["notes"])

    def test_sectioned_flex_style_csv_parses_positions_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "flex.csv"
            source.write_text(
                "\n".join(
                    [
                        "Open Positions,Header,Asset Category,Currency,Symbol,Description,Quantity,Market Value,Market Value in Base,Security Type,Issuer,Report Date",
                        "Open Positions,Data,Stocks,USD,NVDA,NVIDIA Corp,150,20000,20000,STK,NVIDIA,2026-06-08",
                        "Trades,Header,Asset Category,Currency,Symbol,Description,Quantity,Market Value,Market Value in Base,Security Type,Issuer,Report Date",
                        "Trades,Data,Stocks,USD,IGNORED,Ignored trade row,1,1,1,STK,Ignored,2026-06-08",
                    ]
                ),
                encoding="utf-8",
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
            )

            self.assertEqual(len(result.ready_rows), 1)
            self.assertEqual(result.ready_rows[0]["ticker"], "NVDA")

    def test_ambiguous_alias_values_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "ambiguous.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Ticker", "Quantity", "Market Value", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "MSFT",
                        "Ticker": "MSFT_ALT",
                        "Quantity": "1",
                        "Market Value": "100",
                        "Security Type": "STK",
                    }
                ],
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
            )

            self.assertEqual(result.ready_rows[0]["ticker"], "MSFT")
            self.assertTrue(any("ambiguous values" in warning for warning in result.warnings))

    def test_missing_quantity_excludes_row_from_runner_ready_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "missing_quantity.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Market Value", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "TSLA",
                        "Description": "Tesla",
                        "Market Value": "12000",
                        "Security Type": "STK",
                    }
                ],
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
            )

            self.assertEqual(len(result.ready_rows), 0)
            self.assertEqual(result.review_rows[0]["parse_status"], "excluded")
            self.assertTrue(any("missing quantity" in warning for warning in result.warnings))

    def test_non_base_currency_without_base_value_or_fx_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "missing_base.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Quantity", "Market Value", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "HKD",
                        "Symbol": "7709.HK",
                        "Description": "SK Hynix proxy",
                        "Quantity": "1000",
                        "Market Value": "80000",
                        "Security Type": "STK",
                    }
                ],
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
                base_currency="USD",
            )

            self.assertEqual(len(result.ready_rows), 1)
            self.assertTrue(any("non-base-currency row lacks base value and FX rate" in warning for warning in result.warnings))

    def test_runner_ready_output_can_feed_phase3c_runner_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "ibkr.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Quantity", "Market Value", "Market Value in Base", "Security Type", "Issuer"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "MSFT",
                        "Description": "Microsoft Corp",
                        "Quantity": "35",
                        "Market Value": "16000",
                        "Market Value in Base": "16000",
                        "Security Type": "STK",
                        "Issuer": "Microsoft",
                    }
                ],
            )
            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
            )

            runner_result = run_from_paths(
                holdings_path=result.output_files["portfolio_runner_ready_holdings"],
                out_path=tmp_path / "portfolio_report.md",
                json_out_path=tmp_path / "portfolio_summary.json",
            )

            self.assertEqual(len(runner_result.snapshot.holdings), 1)
            self.assertTrue((tmp_path / "portfolio_report.md").exists())
            self.assertTrue((tmp_path / "portfolio_summary.json").exists())

    def test_cli_accepts_statement_alias_and_default_portfolio_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "ibkr.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Quantity", "Market Value", "Market Value in Base", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "MSFT",
                        "Description": "Microsoft Corp",
                        "Quantity": "35",
                        "Market Value": "16000",
                        "Market Value in Base": "16000",
                        "Security Type": "STK",
                    }
                ],
            )
            out_dir = tmp_path / "out"

            exit_code = main(["--statement", str(source), "--out-dir", str(out_dir)])

            self.assertEqual(exit_code, 0)
            payload = json.loads((out_dir / "ibkr_import_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["portfolio_id"], "ibkr_import_review")
            self.assertTrue((out_dir / "parsed_holdings_review.csv").exists())
            self.assertTrue((out_dir / "portfolio_runner_ready_holdings.csv").exists())


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()

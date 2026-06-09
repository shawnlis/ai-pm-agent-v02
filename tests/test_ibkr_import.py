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
            self.assertTrue((tmp_path / "out" / "staged_unverified_holdings.csv").exists())
            self.assertTrue((tmp_path / "out" / "portfolio_runner_ready_holdings.csv").exists())
            self.assertTrue((tmp_path / "out" / "ibkr_import_warnings.md").exists())
            self.assertTrue((tmp_path / "out" / "ibkr_import_summary.json").exists())
            self.assertTrue((tmp_path / "out" / "ibkr_review_manifest.json").exists())
            self.assertTrue(any("cash-like row not converted" in warning for warning in result.warnings))

            candidate_rows = _read_csv(tmp_path / "out" / "staged_unverified_holdings.csv")
            legacy_rows = _read_csv(tmp_path / "out" / "portfolio_runner_ready_holdings.csv")
            self.assertEqual(candidate_rows, legacy_rows)
            self.assertEqual(candidate_rows[0]["ticker"], "MSFT")
            self.assertEqual(candidate_rows[0]["portfolio_id"], "test_ibkr")
            self.assertIn("IBKR_IMPORT_REVIEW_REQUIRED", candidate_rows[0]["notes"])

            manifest = json.loads((tmp_path / "out" / "ibkr_review_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["offline_only"])
            self.assertTrue(manifest["review_required"])
            self.assertFalse(manifest["verified"])
            self.assertEqual(manifest["candidate_rows"], 1)
            self.assertIn("source_file_sha256", manifest)
            self.assertIn("CASH_LIKE_ROW_EXCLUDED", manifest["warnings_by_code"])
            self.assertIn("staged_unverified_holdings", manifest["output_files"])

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

    def test_quarantine_blocks_risky_rows_from_candidate_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "quarantine.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Quantity", "Market Value", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "NO_VALUE",
                        "Description": "Missing market value",
                        "Quantity": "10",
                        "Market Value": "",
                        "Security Type": "STK",
                    },
                    {
                        "Asset Category": "Stocks",
                        "Currency": "USD",
                        "Symbol": "SHORT",
                        "Description": "Short position",
                        "Quantity": "-5",
                        "Market Value": "1000",
                        "Security Type": "STK",
                    },
                    {
                        "Asset Category": "Other",
                        "Currency": "USD",
                        "Symbol": "UNKNOWN",
                        "Description": "Unknown instrument",
                        "Quantity": "1",
                        "Market Value": "100",
                        "Security Type": "MYSTERY",
                    },
                    {
                        "Asset Category": "Options",
                        "Currency": "USD",
                        "Symbol": "OPTROW",
                        "Description": "Option row",
                        "Quantity": "1",
                        "Market Value": "100",
                        "Security Type": "OPT",
                    },
                ],
            )

            result = import_ibkr_statement_files(
                input_paths=[source],
                out_dir=tmp_path / "out",
                portfolio_id="test_ibkr",
                as_of_date="2026-06-08",
            )

            self.assertEqual(len(result.ready_rows), 0)
            self.assertTrue(all(row["parse_status"] == "excluded" for row in result.review_rows))
            all_codes = ";".join(row["warning_codes"] for row in result.review_rows)
            self.assertIn("MISSING_MARKET_VALUE", all_codes)
            self.assertIn("NEGATIVE_QUANTITY", all_codes)
            self.assertIn("UNKNOWN_INSTRUMENT_TYPE", all_codes)
            self.assertIn("UNSUPPORTED_INSTRUMENT_TYPE", all_codes)
            candidate_rows = _read_csv(tmp_path / "out" / "staged_unverified_holdings.csv")
            self.assertEqual(candidate_rows, [])
            manifest = json.loads((tmp_path / "out" / "ibkr_review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["candidate_rows"], 0)
            self.assertEqual(manifest["excluded_rows"], 4)
            self.assertIn("MISSING_MARKET_VALUE", manifest["excluded_by_reason"])
            self.assertIn("NEGATIVE_QUANTITY", manifest["excluded_by_reason"])
            self.assertIn("UNKNOWN_INSTRUMENT_TYPE", manifest["excluded_by_reason"])
            self.assertIn("UNSUPPORTED_INSTRUMENT_TYPE", manifest["excluded_by_reason"])

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

            self.assertEqual(len(result.ready_rows), 0)
            self.assertEqual(result.review_rows[0]["parse_status"], "excluded")
            self.assertIn("NON_BASE_CURRENCY_MISSING_FX", result.review_rows[0]["warning_codes"])
            self.assertTrue(any("non-base-currency row lacks base value and FX rate" in warning for warning in result.warnings))

    def test_missing_currency_column_warns_and_defaults_to_base_currency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "missing_currency_column.csv"
            _write_csv(
                source,
                ["Asset Category", "Symbol", "Description", "Quantity", "Market Value", "Market Value in Base", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Symbol": "MSFT",
                        "Description": "Microsoft Corp",
                        "Quantity": "35",
                        "Market Value": "16000",
                        "Market Value in Base": "16000",
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

            self.assertEqual(len(result.ready_rows), 0)
            self.assertEqual(result.review_rows[0]["trading_currency"], "USD")
            self.assertIn("IBKR_IMPORT_REVIEW_REQUIRED", result.review_rows[0]["notes"])
            self.assertIn("MISSING_CURRENCY", result.review_rows[0]["warning_codes"])
            self.assertTrue(any("MSFT: missing trading currency; defaulted to base currency USD" in warning for warning in result.warnings))

            review_rows = _read_csv(tmp_path / "out" / "parsed_holdings_review.csv")
            self.assertIn("missing trading currency", review_rows[0]["warnings"])
            self.assertIn("MISSING_CURRENCY", review_rows[0]["warning_codes"])
            warnings_markdown = (tmp_path / "out" / "ibkr_import_warnings.md").read_text(encoding="utf-8")
            self.assertIn("missing trading currency; defaulted to base currency USD", warnings_markdown)
            payload = json.loads((tmp_path / "out" / "ibkr_import_summary.json").read_text(encoding="utf-8"))
            self.assertTrue(any("missing trading currency; defaulted to base currency USD" in warning for warning in payload["warnings"]))
            manifest = json.loads((tmp_path / "out" / "ibkr_review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["candidate_rows"], 0)
            self.assertEqual(manifest["warnings_by_code"]["MISSING_CURRENCY"], 1)

    def test_blank_currency_warns_and_defaults_to_base_currency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "blank_currency.csv"
            _write_csv(
                source,
                ["Asset Category", "Currency", "Symbol", "Description", "Quantity", "Market Value", "Market Value in Base", "Security Type"],
                [
                    {
                        "Asset Category": "Stocks",
                        "Currency": "",
                        "Symbol": "NVDA",
                        "Description": "NVIDIA Corp",
                        "Quantity": "10",
                        "Market Value": "12000",
                        "Market Value in Base": "12000",
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

            self.assertEqual(len(result.ready_rows), 0)
            self.assertEqual(result.review_rows[0]["trading_currency"], "USD")
            self.assertIn("IBKR_IMPORT_REVIEW_REQUIRED", result.review_rows[0]["notes"])
            self.assertIn("MISSING_CURRENCY", result.review_rows[0]["warning_codes"])
            self.assertTrue(any("NVDA: missing trading currency; defaulted to base currency USD" in warning for warning in result.warnings))

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
                holdings_path=result.output_files["staged_unverified_holdings"],
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
            self.assertTrue((out_dir / "staged_unverified_holdings.csv").exists())
            self.assertTrue((out_dir / "portfolio_runner_ready_holdings.csv").exists())
            self.assertTrue((out_dir / "ibkr_review_manifest.json").exists())


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

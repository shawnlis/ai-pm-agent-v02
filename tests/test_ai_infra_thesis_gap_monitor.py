from __future__ import annotations

import csv
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.thesis_gap_monitor.evidence_reader import MissingEvidenceInputError, load_from_paths
from ai_pm_agent.thesis_gap_monitor.models import GAP_STATUSES
from ai_pm_agent.thesis_gap_monitor.runner import run_monitor


SCRIPT = ROOT / "scripts" / "ai_infra_thesis_gap_monitor.py"

LEDGER_FIELDS = [
    "company_id",
    "ticker",
    "company_name",
    "cik",
    "source_type",
    "source_name",
    "source_path",
    "source_hash",
    "source_date",
    "evidence_type",
    "evidence_id",
    "metric_or_form",
    "value",
    "unit",
    "period_end",
    "filing_date",
    "confidence",
    "fixture_only",
    "review_status",
]

METRIC_FIELDS = [
    "ticker",
    "company_name",
    "cik",
    "taxonomy",
    "concept",
    "label",
    "unit",
    "value",
    "end_date",
    "filed_date",
    "frame",
    "accession_number",
    "form",
    "fiscal_year",
    "fiscal_period",
    "source_path",
    "source_hash",
    "confidence",
    "fixture_only",
]

GAP_FIELDS = [
    "company",
    "theme",
    "gap_id",
    "gap_question",
    "current_status",
    "evidence_summary",
    "source_count",
    "newest_source_date",
    "confidence",
    "warning_codes",
    "human_review_required",
    "why_it_matters",
    "what_would_close_the_gap",
]


def test_missing_evidence_input_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing_dir = Path(tmp) / "missing"
        try:
            load_from_paths(evidence_dir=missing_dir)
        except MissingEvidenceInputError as exc:
            assert "Missing required evidence files" in str(exc)
        else:
            raise AssertionError("missing evidence input should fail closed")


def test_missing_company_evidence_produces_unknown_not_fabricated_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["NVDA"], as_of_date=_as_of())

        rows = _read_csv(out_dir / "thesis_gap_table.csv")

    assert rows
    assert {row["current_status"] for row in rows} == {"UNKNOWN"}
    assert all("No source-backed evidence rows" in row["evidence_summary"] for row in rows)


def test_stale_evidence_warning_is_emitted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["GOOGL"], as_of_date=_as_of(), stale_days=365)
        warnings_md = (out_dir / "monitor_warnings.md").read_text(encoding="utf-8")

    assert "STALE_EVIDENCE" in warnings_md


def test_report_files_are_generated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        result = run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["MU"], as_of_date=_as_of())
        assert all(Path(path).exists() for path in result["outputs"].values())

    expected = {
        "report",
        "thesis_gap_table",
        "thesis_gap_summary",
        "source_coverage",
        "monitor_warnings",
    }
    assert set(result["outputs"]) == expected


def test_csv_and_json_schemas_are_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["MU"], as_of_date=_as_of())
        gap_rows = _read_csv(out_dir / "thesis_gap_table.csv")
        summary = json.loads((out_dir / "thesis_gap_summary.json").read_text(encoding="utf-8"))

    assert list(gap_rows[0]) == GAP_FIELDS
    assert set(summary["status_counts"]) == set(GAP_STATUSES)
    assert summary["boundary"]["investment_recommendation"] is False
    assert summary["boundary"]["network_access"] is False
    assert summary["boundary"]["live_sec_fetch"] is False


def test_no_network_access_by_default(monkeypatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("thesis-gap monitor must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["MU"], as_of_date=_as_of())
        assert (out_dir / "AI_INFRA_THESIS_GAP_MONITOR_V2.md").exists()


def test_deterministic_classification_from_fixture_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        run_monitor(evidence_dir=evidence_dir, out_dir=out_dir, tickers=["MU", "AMD"], as_of_date=_as_of())
        rows = _read_csv(out_dir / "thesis_gap_table.csv")

    by_company_theme = {(row["company"], row["theme"]): row for row in rows}
    assert by_company_theme[("MU", "HBM / memory")]["current_status"] == "PARTIALLY_CLOSED"
    assert by_company_theme[("MU", "AI capex")]["current_status"] == "WORSENED"
    assert by_company_theme[("AMD", "GPU / accelerator demand")]["current_status"] == "CLOSED"


def test_cli_runs_offline_against_evidence_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        evidence_dir = _write_evidence_bundle(Path(tmp) / "evidence")
        out_dir = Path(tmp) / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--evidence-dir",
                str(evidence_dir),
                "--out-dir",
                str(out_dir),
                "--tickers",
                "MU",
                "--as-of-date",
                "2026-06-13",
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert (out_dir / "AI_INFRA_THESIS_GAP_MONITOR_V2.md").exists()


def test_no_forbidden_pm_or_data_source_imports_or_calls() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "__init__.py",
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "models.py",
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "evidence_reader.py",
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "gap_rules.py",
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "report_writer.py",
        SRC / "ai_pm_agent" / "thesis_gap_monitor" / "runner.py",
        SCRIPT,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    forbidden = [
        "ai_pm_agent.portfolio",
        "portfolio.csv",
        "IBKR Positions",
        "build_pm_prompt",
        "call_llm",
        "OpenRouter",
        "DeepSeek",
        "yfinance",
        "urlopen",
        "requests.",
        "http_client",
    ]
    for pattern in forbidden:
        assert pattern not in combined


def _write_evidence_bundle(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    _write_csv(
        directory / "company_evidence_ledger.csv",
        LEDGER_FIELDS,
        [
            _ledger_row(
                ticker="MU",
                company_name="Micron Technology",
                source_hash="hash_mu_hbm",
                source_date="2026-01-15",
                metric_or_form="HBM qualification sample and production ramp",
                review_status="source_backed",
            ),
            _ledger_row(
                ticker="MU",
                company_name="Micron Technology",
                source_hash="hash_mu_capex",
                source_date="2026-02-01",
                metric_or_form="AI capex for data center infrastructure without revenue monetization",
                review_status="needs_review",
            ),
            _ledger_row(
                ticker="AMD",
                company_name="Advanced Micro Devices",
                source_hash="hash_amd_gpu",
                source_date="2026-03-01",
                metric_or_form="GPU accelerator commercial shipment with material revenue contribution",
                review_status="source_backed",
            ),
            _ledger_row(
                ticker="GOOGL",
                company_name="Alphabet",
                source_hash="hash_googl_cloud",
                source_date="2024-01-01",
                metric_or_form="Cloud infrastructure capex may create data center margin pressure",
                review_status="needs_review",
            ),
        ],
    )
    _write_csv(
        directory / "metric_history.csv",
        METRIC_FIELDS,
        [
            _metric_row(
                ticker="MU",
                company_name="Micron Technology",
                source_hash="hash_mu_metric",
                end_date="2026-02-01",
                filed_date="2026-02-15",
                concept="CapitalExpenditures",
                label="Capital expenditure data center infrastructure",
            ),
            _metric_row(
                ticker="AMD",
                company_name="Advanced Micro Devices",
                source_hash="hash_amd_metric",
                end_date="2026-03-01",
                filed_date="2026-03-15",
                concept="Revenues",
                label="Recognized revenue from GPU accelerator commercial shipment",
            ),
        ],
    )
    manifest = {
        "api_level": "Level 1",
        "fixture_only": False,
        "network_access": False,
        "live_sec_api": False,
        "pm_prompt_wiring": False,
        "warning_codes": [],
        "sources": [
            {
                "ticker": "MU",
                "company_name": "Micron Technology",
                "source_name": "MU fixture evidence",
                "hash_sha256": "hash_mu_hbm",
                "source_date": "2026-01-15",
            },
            {
                "ticker": "AMD",
                "company_name": "Advanced Micro Devices",
                "source_name": "AMD fixture evidence",
                "hash_sha256": "hash_amd_gpu",
                "source_date": "2026-03-01",
            },
        ],
    }
    (directory / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (directory / "ingestion_warnings.md").write_text("# Warnings\n\n- none\n", encoding="utf-8")
    return directory


def _ledger_row(
    *,
    ticker: str,
    company_name: str,
    source_hash: str,
    source_date: str,
    metric_or_form: str,
    review_status: str,
) -> dict[str, str]:
    return {
        "company_id": f"company_{ticker.lower()}",
        "ticker": ticker,
        "company_name": company_name,
        "cik": "",
        "source_type": "SEC_EDGAR_PUBLIC_API",
        "source_name": f"{ticker} official source",
        "source_path": f"cache/{ticker}.json",
        "source_hash": source_hash,
        "source_date": source_date,
        "evidence_type": "metric",
        "evidence_id": f"evidence_{source_hash}",
        "metric_or_form": metric_or_form,
        "value": "",
        "unit": "",
        "period_end": source_date,
        "filing_date": source_date,
        "confidence": "high_official_sec_edgar_public_api",
        "fixture_only": "false",
        "review_status": review_status,
    }


def _metric_row(
    *,
    ticker: str,
    company_name: str,
    source_hash: str,
    end_date: str,
    filed_date: str,
    concept: str,
    label: str,
) -> dict[str, str]:
    return {
        "ticker": ticker,
        "company_name": company_name,
        "cik": "",
        "taxonomy": "us-gaap",
        "concept": concept,
        "label": label,
        "unit": "USD",
        "value": "1",
        "end_date": end_date,
        "filed_date": filed_date,
        "frame": "",
        "accession_number": "",
        "form": "10-Q",
        "fiscal_year": "2026",
        "fiscal_period": "Q1",
        "source_path": f"cache/{ticker}.json",
        "source_hash": source_hash,
        "confidence": "high_official_sec_edgar_public_api",
        "fixture_only": "false",
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_of():
    from datetime import date

    return date(2026, 6, 13)

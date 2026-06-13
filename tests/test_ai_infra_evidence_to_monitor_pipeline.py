from __future__ import annotations

import ast
import csv
from datetime import date
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

from ai_pm_agent.ai_infra_pipeline.report_index import PIPELINE_INDEX_FILENAME
from ai_pm_agent.ai_infra_pipeline.runner import DEFAULT_PIPELINE_BATCH_DIR, run_pipeline
from ai_pm_agent.thesis_gap_monitor.evidence_reader import MissingEvidenceInputError


SCRIPT = ROOT / "scripts" / "ai_infra_evidence_to_monitor_pipeline.py"

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

EXPECTED_INDEX_KEYS = {
    "batch_output_dir",
    "batch_status",
    "companies",
    "evidence_input_dir",
    "error_message",
    "files_created",
    "generated_at",
    "monitor_output_dir",
    "monitor_status",
    "no_broker_data",
    "no_client_data",
    "no_live_sec_fetch",
    "no_llm",
    "no_pm_recommendation_wiring",
    "no_portfolio_data",
    "no_web_search",
    "no_yfinance",
    "run_id",
    "warning_codes",
}


def test_pipeline_can_run_monitor_from_existing_evidence_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = _write_evidence_bundle(root / "evidence")
        monitor_dir = root / "monitor"
        result = run_pipeline(
            evidence_dir=evidence_dir,
            monitor_out_dir=monitor_dir,
            companies=["MU"],
            as_of_date=date(2026, 6, 13),
            offline=True,
        )
        index_path = monitor_dir / PIPELINE_INDEX_FILENAME

        assert result["status"] == "completed"
        assert index_path.exists()
        assert (monitor_dir / "AI_INFRA_THESIS_GAP_MONITOR_V2.md").exists()
        assert (monitor_dir / "thesis_gap_table.csv").exists()


def test_pipeline_index_json_schema_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = _write_evidence_bundle(root / "evidence")
        monitor_dir = root / "monitor"
        run_pipeline(
            evidence_dir=evidence_dir,
            monitor_out_dir=monitor_dir,
            companies=["MU"],
            as_of_date=date(2026, 6, 13),
            offline=True,
        )
        index = json.loads((monitor_dir / PIPELINE_INDEX_FILENAME).read_text(encoding="utf-8"))

    assert set(index) == EXPECTED_INDEX_KEYS
    assert index["batch_status"] == "not_run"
    assert index["monitor_status"] == "completed"
    assert index["no_live_sec_fetch"] is True
    assert index["no_web_search"] is True
    assert index["no_llm"] is True
    assert index["no_yfinance"] is True
    assert index["no_portfolio_data"] is True
    assert index["no_broker_data"] is True
    assert index["no_client_data"] is True
    assert index["no_pm_recommendation_wiring"] is True


def test_missing_evidence_dir_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            run_pipeline(
                evidence_dir=Path(tmp) / "missing",
                monitor_out_dir=Path(tmp) / "monitor",
                companies=["MU"],
                offline=True,
            )
        except MissingEvidenceInputError as exc:
            assert "Evidence input directory does not exist" in str(exc)
        else:
            raise AssertionError("missing evidence directory should fail closed")


def test_existing_evidence_dir_missing_required_files_writes_failure_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        monitor_dir = root / "monitor"
        result = run_pipeline(
            evidence_dir=evidence_dir,
            monitor_out_dir=monitor_dir,
            companies=["MU"],
            offline=True,
        )
        index = json.loads((monitor_dir / PIPELINE_INDEX_FILENAME).read_text(encoding="utf-8"))

    assert result["status"] == "failed"
    assert index["batch_status"] == "not_run"
    assert index["monitor_status"] == "failed"
    assert "MONITOR_FAILED" in index["warning_codes"]
    assert "PIPELINE_FAILED_CLOSED" in index["warning_codes"]
    assert "Missing required evidence files" in index["error_message"]


def test_batch_dry_run_then_monitor_failure_preserves_batch_files_and_cli_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        batch_dir = root / "batch"
        monitor_dir = root / "monitor"
        result = run_pipeline(
            evidence_dir=evidence_dir,
            batch_out_dir=batch_dir,
            monitor_out_dir=monitor_dir,
            run_batch_dry_run=True,
            run_monitor_step=True,
            companies=["MU"],
            offline=True,
        )
        index = json.loads((monitor_dir / PIPELINE_INDEX_FILENAME).read_text(encoding="utf-8"))
        cli_result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--evidence-dir",
                str(evidence_dir),
                "--batch-out-dir",
                str(root / "cli_batch"),
                "--monitor-out-dir",
                str(root / "cli_monitor"),
                "--run-batch-dry-run",
                "--run-monitor",
                "--companies",
                "MU",
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result["status"] == "failed"
    assert index["batch_status"] == "planned"
    assert index["monitor_status"] == "failed"
    assert any(path.endswith("batch_manifest.json") for path in index["files_created"])
    assert "MONITOR_FAILED" in index["warning_codes"]
    assert "PIPELINE_FAILED_CLOSED" in index["warning_codes"]
    assert cli_result.returncode == 2
    assert "AI infra pipeline failed closed" in cli_result.stderr
    assert "AI_INFRA_PIPELINE_INDEX.json" in cli_result.stderr


def test_failure_index_boundary_fields_remain_true() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        monitor_dir = root / "monitor"
        run_pipeline(
            evidence_dir=evidence_dir,
            monitor_out_dir=monitor_dir,
            companies=["MU"],
            offline=True,
        )
        index = json.loads((monitor_dir / PIPELINE_INDEX_FILENAME).read_text(encoding="utf-8"))

    assert index["no_live_sec_fetch"] is True
    assert index["no_web_search"] is True
    assert index["no_llm"] is True
    assert index["no_yfinance"] is True
    assert index["no_portfolio_data"] is True
    assert index["no_broker_data"] is True
    assert index["no_client_data"] is True
    assert index["no_pm_recommendation_wiring"] is True


def test_batch_dry_run_does_not_create_evidence_db() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = Path(tmp) / "batch"
        result = run_pipeline(
            batch_out_dir=batch_dir,
            run_batch_dry_run=True,
            companies=["MU", "NVDA", "AMD", "AVGO", "MSFT", "GOOGL"],
            offline=True,
        )
        index = json.loads((batch_dir / PIPELINE_INDEX_FILENAME).read_text(encoding="utf-8"))
        assert (batch_dir / "batch_manifest.json").exists()
        assert not (batch_dir / "evidence_db.sqlite").exists()

    assert result["status"] == "planned"
    assert index["batch_status"] == "planned"
    assert index["monitor_status"] == "not_run"


def test_no_network_by_default(monkeypatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("pipeline must not open network sockets by default")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = _write_evidence_bundle(root / "evidence")
        run_pipeline(
            evidence_dir=evidence_dir,
            monitor_out_dir=root / "monitor",
            companies=["MU"],
            as_of_date=date(2026, 6, 13),
            offline=True,
        )


def test_no_forbidden_imports_or_calls() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "ai_infra_pipeline" / "__init__.py",
        SRC / "ai_pm_agent" / "ai_infra_pipeline" / "report_index.py",
        SRC / "ai_pm_agent" / "ai_infra_pipeline" / "runner.py",
        ROOT / "scripts" / "ai_infra_evidence_to_monitor_pipeline.py",
    ]
    imported_modules = set()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_imports = {
        "ai_pm_agent.portfolio",
        "yfinance",
        "requests",
        "openai",
        "ib_insync",
    }
    assert forbidden_imports.isdisjoint(imported_modules)
    forbidden_call_markers = [
        "portfolio.csv",
        "IBKR Positions",
        "build_pm_prompt",
        "run_company_research",
        "call_llm",
        "OpenRouter",
        "DeepSeek",
        "place_order",
        "submit_order",
    ]
    for marker in forbidden_call_markers:
        assert marker not in combined


def test_generated_outputs_default_under_ignored_reports_path() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert DEFAULT_PIPELINE_BATCH_DIR.parts[0] == "reports"
    assert "reports/" in gitignore


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

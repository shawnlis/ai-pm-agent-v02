from __future__ import annotations

import ast
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

from ai_pm_agent.opportunity_discovery.loader import MissingOpportunityInputError, load_from_paths
from ai_pm_agent.opportunity_discovery.runner import run_discovery


SCRIPT = ROOT / "scripts" / "ai_infra_opportunity_discovery.py"

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

COVERAGE_FIELDS = [
    "company",
    "company_name",
    "evidence_rows",
    "metric_rows",
    "source_count",
    "newest_source_date",
    "warning_codes",
    "coverage_status",
]

FORBIDDEN_OUTPUT_TERMS = [
    "buy",
    "sell",
    "hold",
    "accumulate",
    "trim",
    "add",
    "reduce",
    "short",
    "long",
    "target price",
    "position size",
    "rebalance",
    "order",
    "trade",
    "roll",
    "close",
    "open position",
]


def test_loads_fixture_inputs_and_writes_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        result = run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)

        assert result["status_counts"]["OPPORTUNITY_REVIEW"] == 1
        assert (out_dir / "AI_INFRA_OPPORTUNITY_REVIEW_QUEUE.md").exists()
        assert (out_dir / "opportunity_candidates.csv").exists()
        assert (out_dir / "opportunity_scorecard.json").exists()
        assert (out_dir / "opportunity_warnings.md").exists()
        assert (out_dir / "opportunity_discovery_manifest.json").exists()
        assert (out_dir / "opportunity_delta_summary.csv").exists()
        assert (out_dir / "opportunity_transition_report.md").exists()


def test_strong_evidence_missing_valuation_is_thesis_improving_not_opportunity_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        rows = _read_csv(out_dir / "opportunity_candidates.csv")

    by_company = {row["company"]: row for row in rows}
    assert by_company["MU"]["status"] == "THESIS_IMPROVING"
    assert by_company["MU"]["status"] != "OPPORTUNITY_REVIEW"
    assert by_company["MU"]["valuation_data_available"] == "false"


def test_missing_source_dates_block_evidence_or_watchlist_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        rows = _read_csv(out_dir / "opportunity_candidates.csv")

    by_company = {row["company"]: row for row in rows}
    assert by_company["AMD"]["status"] in {"EVIDENCE_BLOCKED", "WATCHLIST_ONLY"}
    assert "MISSING_SOURCE_DATE" in by_company["AMD"]["warning_codes"]


def test_valuation_missing_blocks_opportunity_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        rows = _read_csv(out_dir / "opportunity_candidates.csv")

    blocked = [row for row in rows if row["valuation_data_available"] == "false"]
    assert blocked
    assert all(row["status"] != "OPPORTUNITY_REVIEW" for row in blocked)


def test_forbidden_recommendation_words_do_not_appear_in_generated_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in [
                out_dir / "AI_INFRA_OPPORTUNITY_REVIEW_QUEUE.md",
                out_dir / "opportunity_candidates.csv",
                out_dir / "opportunity_scorecard.json",
                out_dir / "opportunity_warnings.md",
                out_dir / "opportunity_discovery_manifest.json",
                out_dir / "opportunity_delta_summary.csv",
                out_dir / "opportunity_transition_report.md",
            ]
        )

    for term in FORBIDDEN_OUTPUT_TERMS:
        assert term not in combined
    assert "not investment advice" in combined


def test_prior_run_promotion_and_downgrade_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        prior_csv = root / "prior_candidates.csv"
        _write_csv(
            prior_csv,
            ["company", "status", "total_score"],
            [
                {"company": "NVDA", "status": "THESIS_IMPROVING", "total_score": "70"},
                {"company": "AMD", "status": "OPPORTUNITY_REVIEW", "total_score": "80"},
            ],
        )
        out_dir = root / "out"
        run_discovery(
            evidence_dir=evidence_dir,
            monitor_dir=monitor_dir,
            prior_candidates_csv=prior_csv,
            out_dir=out_dir,
        )
        delta_rows = _read_csv(out_dir / "opportunity_delta_summary.csv")
        scorecard = json.loads((out_dir / "opportunity_scorecard.json").read_text(encoding="utf-8"))

    by_company = {row["company"]: row for row in delta_rows}
    assert by_company["NVDA"]["status_change"] == "PROMOTED"
    assert by_company["NVDA"]["newly_promoted"] == "true"
    assert by_company["AMD"]["status_change"] == "DOWNGRADED"
    assert by_company["AMD"]["newly_downgraded"] == "true"
    assert any(candidate["status_change"] == "PROMOTED" for candidate in scorecard["candidates"])


def test_high_risk_summary_sets_risk_blocked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        risk_csv = root / "risk_warning_summary.csv"
        _write_csv(
            risk_csv,
            ["ticker", "severity", "warning_code", "message"],
            [{"ticker": "NVDA", "severity": "high", "warning_code": "HIGH_RISK_BLOCKER", "message": "fixture risk"}],
        )
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, risk_summary_path=risk_csv, out_dir=out_dir)
        rows = _read_csv(out_dir / "opportunity_candidates.csv")

    by_company = {row["company"]: row for row in rows}
    assert by_company["NVDA"]["status"] == "RISK_BLOCKED"
    assert "HIGH_RISK_BLOCKER_PRESENT" in by_company["NVDA"]["warning_codes"]


def test_opportunity_review_contains_required_explanation_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        rows = _read_csv(out_dir / "opportunity_candidates.csv")

    nvda = {row["company"]: row for row in rows}["NVDA"]
    assert nvda["status"] == "OPPORTUNITY_REVIEW"
    for field in [
        "why_this_status",
        "what_would_upgrade",
        "what_would_downgrade",
        "unresolved_blockers",
        "required_next_evidence",
        "not_investment_advice",
    ]:
        assert field in nvda
    assert nvda["why_this_status"]
    assert nvda["what_would_upgrade"]
    assert nvda["what_would_downgrade"]
    assert nvda["required_next_evidence"]
    assert nvda["not_investment_advice"] == "true"


def test_manifest_records_inputs_and_safety_flags() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        manifest = json.loads((out_dir / "opportunity_discovery_manifest.json").read_text(encoding="utf-8"))

    assert manifest["input_paths"]["evidence_dir"] == str(evidence_dir)
    assert manifest["input_paths"]["monitor_dir"] == str(monitor_dir)
    assert manifest["prior_run_used"] is False
    assert manifest["risk_summary_used"] is False
    assert manifest["safety"]["pm_prompt_wiring"] is False
    assert manifest["safety"]["portfolio_data_used"] is False
    assert manifest["safety"]["broker_data_used"] is False
    assert manifest["safety"]["client_data_used"] is False
    assert manifest["safety"]["network_access"] is False
    assert manifest["safety"]["llm"] is False
    assert manifest["safety"]["yfinance"] is False


def test_missing_required_inputs_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir = root / "evidence"
        monitor_dir = root / "monitor"
        evidence_dir.mkdir()
        monitor_dir.mkdir()
        try:
            load_from_paths(evidence_dir=evidence_dir, monitor_dir=monitor_dir)
        except MissingOpportunityInputError as exc:
            assert "Missing required opportunity discovery inputs" in str(exc)
        else:
            raise AssertionError("missing inputs should fail closed")


def test_disallowed_portfolio_ibkr_broker_client_paths_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        unsafe_paths = [
            root / "portfolio.csv",
            root / "IBKR Positions" / "risk_warning_summary.csv",
            root / "broker_warning_summary.csv",
            root / "client_warning_summary.csv",
        ]
        for unsafe_path in unsafe_paths:
            try:
                run_discovery(
                    evidence_dir=evidence_dir,
                    monitor_dir=monitor_dir,
                    risk_summary_path=unsafe_path,
                    out_dir=root / f"out_{unsafe_path.name}",
                )
            except MissingOpportunityInputError as exc:
                assert "Unsafe optional opportunity discovery path rejected" in str(exc)
            else:
                raise AssertionError(f"unsafe path should fail closed: {unsafe_path}")


def test_deterministic_ordering() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_one = root / "out_one"
        out_two = root / "out_two"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_one)
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_two)
        rows_one = _read_csv(out_one / "opportunity_candidates.csv")
        rows_two = _read_csv(out_two / "opportunity_candidates.csv")

    assert [row["company"] for row in rows_one] == [row["company"] for row in rows_two]
    assert [row["status"] for row in rows_one] == [row["status"] for row in rows_two]


def test_no_network_by_default(monkeypatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("opportunity discovery must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        run_discovery(evidence_dir=evidence_dir, monitor_dir=monitor_dir, out_dir=out_dir)
        assert (out_dir / "opportunity_candidates.csv").exists()


def test_cli_runs_offline_against_fixture_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence_dir, monitor_dir = _write_fixture_bundle(root)
        out_dir = root / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--evidence-dir",
                str(evidence_dir),
                "--monitor-dir",
                str(monitor_dir),
                "--out-dir",
                str(out_dir),
                "--offline",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    assert "OPPORTUNITY_REVIEW" in result.stdout


def test_no_pm_prompt_wiring_or_forbidden_imports() -> None:
    source_files = [
        SRC / "ai_pm_agent" / "opportunity_discovery" / "__init__.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "models.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "loader.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "scoring.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "exports.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "runner.py",
        SRC / "ai_pm_agent" / "opportunity_discovery" / "warnings.py",
        SCRIPT,
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
        "ai_pm_agent.portfolio_risk_cockpit",
        "ai_pm_agent.risk_cockpit_pipeline",
        "yfinance",
        "requests",
        "openai",
        "ib_insync",
    }
    assert forbidden_imports.isdisjoint(imported_modules)
    for marker in [
        "build_pm_prompt",
        "run_company_research",
        "call_llm",
        "OpenRouter",
        "DeepSeek",
        "place_order",
        "submit_order",
    ]:
        assert marker not in combined


def _write_fixture_bundle(root: Path) -> tuple[Path, Path]:
    evidence_dir = root / "evidence"
    monitor_dir = root / "monitor"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    monitor_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        evidence_dir / "company_evidence_ledger.csv",
        LEDGER_FIELDS,
        [
            _ledger_row(
                ticker="NVDA",
                company_name="NVIDIA",
                source_hash="hash_nvda_accel",
                source_date="2026-04-01",
                metric_or_form="GPU accelerator commercial shipment with material revenue contribution and customer commitment",
            ),
            _ledger_row(
                ticker="NVDA",
                company_name="NVIDIA",
                source_hash="hash_nvda_valuation",
                source_date="2026-04-02",
                metric_or_form="valuation multiple and free cash flow yield evidence available",
            ),
            _ledger_row(
                ticker="MU",
                company_name="Micron Technology",
                source_hash="hash_mu_hbm",
                source_date="2026-03-15",
                metric_or_form="HBM volume production with revenue contribution and customer commitment",
            ),
            _ledger_row(
                ticker="AMD",
                company_name="Advanced Micro Devices",
                source_hash="hash_amd_undated",
                source_date="",
                metric_or_form="GPU accelerator commercial shipment evidence",
            ),
            _ledger_row(
                ticker="AVGO",
                company_name="Broadcom",
                source_hash="hash_avgo_risk",
                source_date="2026-02-01",
                metric_or_form="custom silicon backlog with customer concentration risk evidence",
            ),
        ],
    )
    _write_csv(
        evidence_dir / "metric_history.csv",
        METRIC_FIELDS,
        [
            _metric_row(
                ticker="NVDA",
                company_name="NVIDIA",
                source_hash="hash_nvda_metric",
                end_date="2026-04-02",
                filed_date="2026-04-15",
                concept="FreeCashFlowYield",
                label="valuation free cash flow yield",
            ),
            _metric_row(
                ticker="MU",
                company_name="Micron Technology",
                source_hash="hash_mu_metric",
                end_date="2026-03-15",
                filed_date="2026-03-30",
                concept="Revenues",
                label="revenue contribution from HBM",
            ),
        ],
    )
    (evidence_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "api_level": "Level 1",
                "fixture_only": True,
                "network_access": False,
                "live_sec_api": False,
                "pm_prompt_wiring": False,
                "warning_codes": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    gap_rows = [
        _gap_row("NVDA", "GPU / accelerator demand", "CLOSED", "commercial shipment material revenue", 2, "2026-04-02"),
        _gap_row("NVDA", "revenue recognition / backlog / deferred revenue", "PARTIALLY_CLOSED", "customer commitment backlog", 2, "2026-04-02"),
        _gap_row("MU", "HBM / memory", "CLOSED", "volume production revenue contribution", 2, "2026-03-15"),
        _gap_row("MU", "revenue recognition / backlog / deferred revenue", "PARTIALLY_CLOSED", "customer commitment backlog", 2, "2026-03-15"),
        _gap_row("AMD", "GPU / accelerator demand", "CLOSED", "commercial shipment", 1, "", warning_codes="MISSING_SOURCE_DATE"),
        _gap_row("AVGO", "networking / ASIC / custom silicon", "PARTIALLY_CLOSED", "custom silicon backlog", 1, "2026-02-01", warning_codes="RISK_EVIDENCE_PRESENT"),
    ]
    _write_csv(monitor_dir / "thesis_gap_table.csv", GAP_FIELDS, gap_rows)
    (monitor_dir / "thesis_gap_summary.json").write_text(
        json.dumps({"status_counts": {"CLOSED": 3, "PARTIALLY_CLOSED": 3}, "boundary": {"investment_recommendation": False}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    _write_csv(
        monitor_dir / "source_coverage.csv",
        COVERAGE_FIELDS,
        [
            _coverage_row("NVDA", "NVIDIA", 2, 1, 3, "2026-04-02", "COVERED"),
            _coverage_row("MU", "Micron Technology", 1, 1, 2, "2026-03-15", "COVERED"),
            _coverage_row("AMD", "Advanced Micro Devices", 1, 0, 1, "", "NEEDS_REVIEW", "MISSING_SOURCE_DATE"),
            _coverage_row("AVGO", "Broadcom", 1, 0, 1, "2026-02-01", "COVERED", "RISK_EVIDENCE_PRESENT"),
        ],
    )
    (monitor_dir / "monitor_warnings.md").write_text("# Monitor Warnings\n\n- fixture only\n", encoding="utf-8")
    return evidence_dir, monitor_dir


def _ledger_row(
    *,
    ticker: str,
    company_name: str,
    source_hash: str,
    source_date: str,
    metric_or_form: str,
) -> dict[str, str]:
    return {
        "company_id": f"company_{ticker.lower()}",
        "ticker": ticker,
        "company_name": company_name,
        "cik": "",
        "source_type": "SEC_EDGAR_PUBLIC_API",
        "source_name": f"{ticker} fixture source",
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
        "fixture_only": "true",
        "review_status": "source_backed",
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
        "fixture_only": "true",
    }


def _gap_row(
    company: str,
    theme: str,
    status: str,
    summary: str,
    source_count: int,
    newest_source_date: str,
    warning_codes: str = "",
) -> dict[str, str]:
    return {
        "company": company,
        "theme": theme,
        "gap_id": f"gap_{company.lower()}_{theme.lower().replace(' ', '_')[:8]}",
        "gap_question": "fixture question",
        "current_status": status,
        "evidence_summary": summary,
        "source_count": str(source_count),
        "newest_source_date": newest_source_date,
        "confidence": "high",
        "warning_codes": warning_codes,
        "human_review_required": "false",
        "why_it_matters": "fixture",
        "what_would_close_the_gap": "fixture",
    }


def _coverage_row(
    company: str,
    company_name: str,
    evidence_rows: int,
    metric_rows: int,
    source_count: int,
    newest_source_date: str,
    coverage_status: str,
    warning_codes: str = "",
) -> dict[str, str]:
    return {
        "company": company,
        "company_name": company_name,
        "evidence_rows": str(evidence_rows),
        "metric_rows": str(metric_rows),
        "source_count": str(source_count),
        "newest_source_date": newest_source_date,
        "warning_codes": warning_codes,
        "coverage_status": coverage_status,
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

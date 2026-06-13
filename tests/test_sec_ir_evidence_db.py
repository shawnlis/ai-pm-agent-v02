from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.evidence_db.exports import export_all
from ai_pm_agent.evidence_db.models import IngestionRun, stable_id, utc_now
from ai_pm_agent.evidence_db.repository import EvidenceRepository
from ai_pm_agent.evidence_db import http_client
from ai_pm_agent.evidence_db.sec_edgar import (
    build_evidence_claims,
    dry_run_fixtures,
    import_fixtures,
    parse_companyfacts_fixture,
    parse_submissions_fixture,
)
from ai_pm_agent.evidence_db.warnings import MISSING_FACT_VALUE, MISSING_FILING_DATE, SOURCE_FIXTURE_ONLY


SUBMISSIONS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_submissions_sample.json"
COMPANYFACTS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_companyfacts_sample.json"
SCRIPT = ROOT / "scripts" / "sec_ir_evidence_import.py"


def test_parse_submissions_fixture() -> None:
    parsed = parse_submissions_fixture(SUBMISSIONS_FIXTURE, ticker="MU", company_name="Micron Technology")

    assert parsed.company.ticker == "MU"
    assert parsed.company.cik == "723125"
    assert parsed.company.cik_padded == "0000723125"
    assert parsed.source_document.fixture_only is True
    assert len(parsed.filings) == 3
    assert parsed.filings[0].form == "10-Q"
    assert any(warning.code == SOURCE_FIXTURE_ONLY for warning in parsed.warnings)


def test_parse_companyfacts_fixture() -> None:
    parsed = parse_companyfacts_fixture(COMPANYFACTS_FIXTURE, ticker="MU", company_name="Micron Technology")

    assert parsed.company.ticker == "MU"
    assert parsed.source_document.fixture_only is True
    assert len(parsed.facts) == 7
    concepts = {fact.concept for fact in parsed.facts}
    assert "Revenues" in concepts
    assert "Assets" in concepts
    assert all(fact.confidence == "high_fixture_official_shape" for fact in parsed.facts)
    assert any(warning.code == SOURCE_FIXTURE_ONLY for warning in parsed.warnings)


def test_initialize_sqlite_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "evidence.sqlite"
        with EvidenceRepository(db_path) as repo:
            assert repo.table_count("companies") == 0
            assert repo.table_count("source_documents") == 0
            assert repo.table_count("sec_filings") == 0
            assert repo.table_count("xbrl_facts") == 0


def test_insert_company_filings_and_facts() -> None:
    submissions = parse_submissions_fixture(SUBMISSIONS_FIXTURE, ticker="MU", company_name="Micron Technology")
    companyfacts = parse_companyfacts_fixture(COMPANYFACTS_FIXTURE, ticker="MU", company_name="Micron Technology")
    claims = build_evidence_claims(companyfacts.facts, submissions.company)
    run = IngestionRun(
        run_id=stable_id("run", "unit", utc_now()),
        ticker="MU",
        company_name="Micron Technology",
        started_at=utc_now(),
        completed_at=utc_now(),
        source_mode="fixture_only",
        fixture_only=True,
        status="completed",
        warnings_count=0,
        errors_count=0,
        output_dir="",
    )

    with tempfile.TemporaryDirectory() as tmp:
        with EvidenceRepository(Path(tmp) / "evidence.sqlite") as repo:
            repo.insert_ingestion_run(run)
            repo.insert_company(submissions.company)
            repo.insert_source_document(submissions.source_document)
            repo.insert_source_document(companyfacts.source_document)
            for filing in submissions.filings:
                repo.insert_sec_filing(filing)
            for fact in companyfacts.facts:
                repo.insert_xbrl_fact(fact)
            for claim in claims:
                repo.insert_evidence_claim(claim)
            repo.commit()

            assert repo.table_count("companies") == 1
            assert repo.table_count("sec_filings") == 3
            assert repo.table_count("xbrl_facts") == 7
            assert repo.table_count("evidence_claims") == 7


def test_export_csv_json_and_markdown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        outputs = import_fixtures(
            submissions_fixture=SUBMISSIONS_FIXTURE,
            companyfacts_fixture=COMPANYFACTS_FIXTURE,
            ticker="MU",
            company_name="Micron Technology",
            out_dir=out_dir,
        )

        assert Path(outputs["company_evidence_ledger"]).exists()
        assert Path(outputs["metric_history"]).exists()
        assert Path(outputs["source_manifest"]).exists()
        assert Path(outputs["ingestion_warnings"]).exists()
        assert Path(outputs["fixture_mvp_report"]).exists()

        with Path(outputs["company_evidence_ledger"]).open("r", encoding="utf-8", newline="") as handle:
            ledger_rows = list(csv.DictReader(handle))
        assert len(ledger_rows) == 10

        manifest = json.loads(Path(outputs["source_manifest"]).read_text(encoding="utf-8"))
        assert manifest["fixture_only"] is True
        assert manifest["live_sec_api"] is False
        assert manifest["pm_prompt_wiring"] is False

        warnings_md = Path(outputs["ingestion_warnings"]).read_text(encoding="utf-8")
        assert SOURCE_FIXTURE_ONLY in warnings_md


def test_missing_fixture_field_produces_warning() -> None:
    payload = json.loads(SUBMISSIONS_FIXTURE.read_text(encoding="utf-8"))
    payload["filings"]["recent"]["filingDate"][1] = None
    parsed = parse_submissions_fixture(payload, ticker="MU", company_name="Micron Technology")

    assert any(warning.code == MISSING_FILING_DATE for warning in parsed.warnings)

    facts_payload = json.loads(COMPANYFACTS_FIXTURE.read_text(encoding="utf-8"))
    facts_payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0].pop("val")
    parsed_facts = parse_companyfacts_fixture(facts_payload, ticker="MU", company_name="Micron Technology")

    assert any(warning.code == MISSING_FACT_VALUE for warning in parsed_facts.warnings)


def test_fixture_only_flag_appears_in_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        outputs = import_fixtures(
            submissions_fixture=SUBMISSIONS_FIXTURE,
            companyfacts_fixture=COMPANYFACTS_FIXTURE,
            ticker="MU",
            company_name="Micron Technology",
            out_dir=out_dir,
        )
        manifest = json.loads(Path(outputs["source_manifest"]).read_text(encoding="utf-8"))

        assert manifest["fixture_only"] is True
        assert all(source["fixture_only"] is True for source in manifest["sources"])


def test_no_network_call_occurs_in_fixture_mode(monkeypatch) -> None:
    calls: list[str] = []

    def fail_fetch(*args, **kwargs):
        calls.append("fetch")
        raise AssertionError("fixture mode must not call HTTP")

    monkeypatch.setattr(http_client, "fetch_json", fail_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        outputs = import_fixtures(
            submissions_fixture=SUBMISSIONS_FIXTURE,
            companyfacts_fixture=COMPANYFACTS_FIXTURE,
            ticker="MU",
            company_name="Micron Technology",
            out_dir=Path(tmp) / "out",
        )

    assert calls == []
    assert outputs["facts_count"] == 7


def test_cli_dry_run_works() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ticker",
                "MU",
                "--company-name",
                "Micron Technology",
                "--submissions-fixture",
                str(SUBMISSIONS_FIXTURE),
                "--companyfacts-fixture",
                str(COMPANYFACTS_FIXTURE),
                "--out-dir",
                str(Path(tmp) / "out"),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["fixture_only"] is True
    assert payload["facts_count"] == 7


def test_cli_fixture_import_works_to_tempdir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ticker",
                "MU",
                "--company-name",
                "Micron Technology",
                "--submissions-fixture",
                str(SUBMISSIONS_FIXTURE),
                "--companyfacts-fixture",
                str(COMPANYFACTS_FIXTURE),
                "--out-dir",
                str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert (out_dir / "evidence_db.sqlite").exists()
        assert (out_dir / "company_evidence_ledger.csv").exists()
        assert (out_dir / "metric_history.csv").exists()
        assert (out_dir / "source_manifest.json").exists()
        assert (out_dir / "ingestion_warnings.md").exists()
        assert (out_dir / "SEC_IR_EVIDENCE_DB_FIXTURE_MVP_REPORT.md").exists()


def test_source_manifest_contains_path_hash_date_and_confidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        outputs = import_fixtures(
            submissions_fixture=SUBMISSIONS_FIXTURE,
            companyfacts_fixture=COMPANYFACTS_FIXTURE,
            ticker="MU",
            company_name="Micron Technology",
            out_dir=Path(tmp) / "out",
        )
        manifest = json.loads(Path(outputs["source_manifest"]).read_text(encoding="utf-8"))

        assert len(manifest["sources"]) == 2
        for source in manifest["sources"]:
            assert source["path"]
            assert len(source["hash_sha256"]) == 64
            assert source["source_date"]
            assert source["confidence"] == "high_fixture_official_shape"


def test_pm_prompt_path_is_not_touched() -> None:
    evidence_sources = [
        SRC / "ai_pm_agent" / "evidence_db" / "__init__.py",
        SRC / "ai_pm_agent" / "evidence_db" / "models.py",
        SRC / "ai_pm_agent" / "evidence_db" / "sec_edgar.py",
        SRC / "ai_pm_agent" / "evidence_db" / "repository.py",
        SRC / "ai_pm_agent" / "evidence_db" / "exports.py",
        SRC / "ai_pm_agent" / "evidence_db" / "warnings.py",
        SRC / "ai_pm_agent" / "evidence_db" / "http_client.py",
        SRC / "ai_pm_agent" / "evidence_db" / "cache.py",
        SCRIPT,
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in evidence_sources)

    assert "build_pm_prompt" not in combined
    assert "run_company_research" not in combined
    assert "read_portfolio" not in combined
    assert "portfolio.csv" not in combined
    assert "IBKR Positions" not in combined


def test_export_only_from_existing_database() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        first_out = Path(tmp) / "first"
        outputs = import_fixtures(
            submissions_fixture=SUBMISSIONS_FIXTURE,
            companyfacts_fixture=COMPANYFACTS_FIXTURE,
            ticker="MU",
            company_name="Micron Technology",
            out_dir=first_out,
        )
        second_out = Path(tmp) / "second"
        with EvidenceRepository(outputs["database"], read_only=True) as repo:
            exported = export_all(repo, second_out)

        assert Path(exported["company_evidence_ledger"]).exists()
        assert Path(exported["source_manifest"]).exists()

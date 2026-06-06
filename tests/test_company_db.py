from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SMOKE_SCRIPT = ROOT / "scripts" / "company_db_smoke_test.py"
SMOKE_SPEC = importlib.util.spec_from_file_location("company_db_smoke_test", SMOKE_SCRIPT)
company_db_smoke_test = importlib.util.module_from_spec(SMOKE_SPEC)
sys.modules["company_db_smoke_test"] = company_db_smoke_test
assert SMOKE_SPEC.loader is not None
SMOKE_SPEC.loader.exec_module(company_db_smoke_test)

from ai_pm_agent.artifacts.importer import CompanyDbImporter
from ai_pm_agent.approval.manifest import MANIFEST_FIELDS
from ai_pm_agent.approval.packet import ApprovalPacketGenerator, ApprovalPacketOptions
from ai_pm_agent.approval.runbook import RUNBOOK_CSV_FIELDS, ManualRunbookGenerator
from ai_pm_agent.approval.validator import (
    ApprovalManifestValidator,
    VALIDATED_MANIFEST_FIELDS,
    dangerous_command_patterns,
    parse_approved_value,
)
from ai_pm_agent.cli.company_approval import main as company_approval_cli_main
from ai_pm_agent.cli.company_db import main as company_db_cli_main
from ai_pm_agent.cli.company_refresh import main as company_refresh_cli_main
from ai_pm_agent.cli.company_reports import main as company_reports_cli_main
from ai_pm_agent.company_db.repository import CompanyResearchRepository, DecisionFilters
from ai_pm_agent.refresh.planner import RefreshPlanner
from ai_pm_agent.refresh.scoring import score_refresh_candidate
from ai_pm_agent.reports.company_dossier import CompanyDossierGenerator
from ai_pm_agent.reports.watchlist_reports import WatchlistReportGenerator


class CompanyDbImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.outputs = self.root / "outputs"
        self.db = self.root / "data" / "company_db" / "company_research.sqlite"
        self.outputs.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_initialization(self) -> None:
        with CompanyResearchRepository(self.db) as repo:
            self.assertEqual(repo.table_count("research_runs"), 0)
            self.assertEqual(repo.table_count("pm_decisions"), 0)

    def test_import_complete_artifact_folder(self) -> None:
        run_dir = self.write_complete_run("ABC", "20260101", "010203")
        self.write_research_log([run_dir])

        summary = CompanyDbImporter(self.outputs, self.db).import_outputs()

        self.assertEqual(summary.discovered, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(summary.warnings, 0)
        with CompanyResearchRepository(self.db) as repo:
            self.assertEqual(repo.table_count("research_runs"), 1)
            self.assertEqual(repo.table_count("pm_decisions"), 1)
            self.assertEqual(repo.table_count("market_snapshots"), 1)
            self.assertEqual(repo.table_count("evidence_items"), 1)
            self.assertEqual(repo.table_count("facts"), 2)
            self.assertGreaterEqual(repo.table_count("artifact_files"), 10)

    def test_missing_optional_files_records_warnings(self) -> None:
        self.write_minimal_run("MISS", "20260101", "010203")

        summary = CompanyDbImporter(self.outputs, self.db).import_outputs()

        self.assertEqual(summary.discovered, 1)
        self.assertEqual(summary.imported, 1)
        self.assertGreater(summary.warnings, 0)
        with CompanyResearchRepository(self.db) as repo:
            self.assertGreater(repo.table_count("import_warnings"), 0)

    def test_idempotent_reimport(self) -> None:
        run_dir = self.write_complete_run("IDEM", "20260101", "010203")
        self.write_research_log([run_dir])
        importer = CompanyDbImporter(self.outputs, self.db)

        importer.import_outputs()
        importer.import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            self.assertEqual(repo.table_count("research_runs"), 1)
            self.assertEqual(repo.table_count("pm_decisions"), 1)
            self.assertEqual(repo.table_count("evidence_items"), 1)
            self.assertEqual(repo.table_count("facts"), 2)

    def test_malformed_json_records_warning(self) -> None:
        run_dir = self.run_dir("BAD", "20260101", "010203")
        run_dir.mkdir(parents=True)
        (run_dir / "pm_decision.json").write_text("{not valid json", encoding="utf-8")

        summary = CompanyDbImporter(self.outputs, self.db).import_outputs()

        self.assertEqual(summary.discovered, 1)
        self.assertEqual(summary.imported, 1)
        with CompanyResearchRepository(self.db) as repo:
            self.assertEqual(repo.table_count("research_runs"), 1)
            self.assertEqual(repo.table_count("pm_decisions"), 0)
            self.assertGreater(repo.table_count("import_warnings"), 0)

    def test_list_latest_company_decisions(self) -> None:
        older = self.write_complete_run("LIST", "20260101", "010203", action="watchlist")
        newer = self.write_complete_run("LIST", "20260201", "010203", action="buy")
        self.write_research_log([older, newer])

        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.get_company_decisions("LIST")
        self.assertEqual(rows[0]["action"], "buy")
        self.assertEqual(rows[1]["action"], "watchlist")

    def test_import_warnings_are_queryable(self) -> None:
        self.write_minimal_run("WARN", "20260101", "010203")

        CompanyDbImporter(self.outputs, self.db).import_outputs()

        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT warning_type FROM import_warnings ORDER BY warning_type LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertIn(row["warning_type"], {"missing_optional_artifact", "research_log_unmatched"})

    def test_latest_decision_query_uses_latest_per_ticker(self) -> None:
        older = self.write_complete_run("LAT", "20260101", "010203", action="watchlist")
        newer = self.write_complete_run("LAT", "20260201", "010203", action="buy")
        other = self.write_complete_run("OTH", "20260115", "010203", action="watchlist")
        self.write_research_log([older, newer, other])

        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.list_latest_decisions()
        self.assertEqual({row["ticker"] for row in rows}, {"LAT", "OTH"})
        lat = [row for row in rows if row["ticker"] == "LAT"][0]
        self.assertEqual(lat["action"], "buy")

    def test_filter_by_ticker(self) -> None:
        first = self.write_complete_run("FLT", "20260101", "010203")
        second = self.write_complete_run("XXX", "20260101", "010204")
        self.write_research_log([first, second])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.filter_decisions(filters=DecisionFilters(ticker="FLT"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "FLT")

    def test_filter_by_action_and_rating(self) -> None:
        buy = self.write_complete_run("BUY", "20260101", "010203", action="buy", rating="A")
        watch = self.write_complete_run("WAT", "20260101", "010204", action="watchlist", rating="B")
        self.write_research_log([buy, watch])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.filter_decisions(filters=DecisionFilters(action="buy", rating="A"))
        self.assertEqual([row["ticker"] for row in rows], ["BUY"])

    def test_chokepoint_score_filters(self) -> None:
        high = self.write_complete_run("HI", "20260101", "010203", chokepoint_score=91)
        low = self.write_complete_run("LO", "20260101", "010204", chokepoint_score=45)
        self.write_research_log([high, low])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.filter_decisions(
                filters=DecisionFilters(min_chokepoint_score=80, max_chokepoint_score=95)
            )
        self.assertEqual([row["ticker"] for row in rows], ["HI"])

    def test_history_for_ticker(self) -> None:
        older = self.write_complete_run("HIS", "20260101", "010203", action="watchlist")
        newer = self.write_complete_run("HIS", "20260201", "010203", action="buy")
        self.write_research_log([older, newer])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.compare_ticker_history("HIS")
        self.assertEqual([row["action"] for row in rows], ["buy", "watchlist"])

    def test_ranking_by_chokepoint_score(self) -> None:
        top = self.write_complete_run("TOP", "20260101", "010203", chokepoint_score=95)
        mid = self.write_complete_run("MID", "20260101", "010204", chokepoint_score=65)
        self.write_research_log([top, mid])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.rank_by_chokepoint_score(limit=2)
        self.assertEqual([row["ticker"] for row in rows], ["TOP", "MID"])

    def test_warnings_query(self) -> None:
        self.write_minimal_run("WRN", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.list_import_warnings(ticker="WRN", limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["ticker"], "WRN")

    def test_stale_or_incomplete_query(self) -> None:
        self.write_minimal_run("INC", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            rows = repo.list_stale_or_incomplete_companies()
        self.assertEqual(rows[0]["ticker"], "INC")
        self.assertEqual(rows[0]["has_market_snapshot"], 0)

    def test_csv_export(self) -> None:
        run_dir = self.write_complete_run("CSV", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "exports" / "latest.csv"

        exit_code = company_db_cli_main(
            ["export-csv", "--db", str(self.db), "--out", str(out), "--limit", "10"]
        )

        self.assertEqual(exit_code, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("ticker,company_name,market,action,rating", text)
        self.assertIn("CSV,CSV Corp,US,watchlist,B", text)

    def test_null_missing_score_handling(self) -> None:
        self.write_minimal_run("NULL", "20260101", "010203")
        scored = self.write_complete_run("SCR", "20260101", "010204", pm_score=88)
        self.write_research_log([scored])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            ranked = repo.rank_by_pm_score(limit=10)
            filtered = repo.filter_decisions(filters=DecisionFilters(min_pm_score=80))
        self.assertEqual(ranked[0]["ticker"], "SCR")
        self.assertEqual([row["ticker"] for row in filtered], ["SCR"])

    def test_single_company_dossier_generation(self) -> None:
        run_dir = self.write_complete_run("DOS", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            markdown = CompanyDossierGenerator(repo).generate("DOS")

        self.assertIn("# Company Dossier: DOS - DOS Corp", markdown)
        self.assertIn("## 1. Latest Decision Summary", markdown)
        self.assertIn("## 6. Historical Decision Timeline", markdown)

    def test_dossier_generation_with_missing_optional_fields(self) -> None:
        self.write_minimal_run("MIN", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            markdown = CompanyDossierGenerator(repo).generate("MIN")

        self.assertIn("No market_snapshot row is indexed", markdown)
        self.assertIn("No evidence_items are indexed", markdown)
        self.assertIn("No facts are indexed", markdown)

    def test_top_chokepoint_report_generation(self) -> None:
        top = self.write_complete_run("RPT", "20260101", "010203", chokepoint_score=90)
        low = self.write_complete_run("LOW", "20260101", "010204", chokepoint_score=20)
        self.write_research_log([top, low])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            output = WatchlistReportGenerator(repo).top_chokepoints(limit=2)

        self.assertIn("# Top Chokepoint Report", output.markdown)
        self.assertIn("Rule-Based Observations", output.markdown)
        self.assertEqual(output.csv_fields[0], "ticker")

    def test_latest_decisions_report_generation(self) -> None:
        run_dir = self.write_complete_run("LDR", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            output = WatchlistReportGenerator(repo).latest_decisions(limit=5)

        self.assertIn("# Latest Decisions Report", output.markdown)
        self.assertIn("Action counts", output.markdown)

    def test_stale_and_warnings_report_generation(self) -> None:
        self.write_minimal_run("STA", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            stale = WatchlistReportGenerator(repo).stale(limit=5)
            warnings = WatchlistReportGenerator(repo).warnings(limit=5)

        self.assertIn("# Stale / Incomplete Company Data Report", stale.markdown)
        self.assertIn("# Import Warning Summary Report", warnings.markdown)
        self.assertIn("missing_optional_artifact", warnings.markdown)

    def test_decision_history_rendering(self) -> None:
        older = self.write_complete_run("CHG", "20260101", "010203", action="watchlist", pm_score=40)
        newer = self.write_complete_run("CHG", "20260201", "010203", action="buy", pm_score=80)
        self.write_research_log([older, newer])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            dossier = CompanyDossierGenerator(repo).generate("CHG")
            changes = WatchlistReportGenerator(repo).decision_changes(limit=10)

        self.assertIn("buy", dossier)
        self.assertIn("watchlist", dossier)
        self.assertIn("# Decision Change Report", changes.markdown)
        self.assertIn("CHG", changes.markdown)

    def test_report_handles_empty_evidence_and_facts(self) -> None:
        self.write_minimal_run("EMP", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            output = WatchlistReportGenerator(repo).top_chokepoints(limit=10)

        self.assertIn("Missing evidence rows", output.markdown)
        self.assertIn("Missing fact rows", output.markdown)

    def test_report_handles_null_numeric_scores(self) -> None:
        run_dir = self.write_complete_run("NUL", "20260101", "010203", pm_score=None, chokepoint_score=None)
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            dossier = CompanyDossierGenerator(repo).generate("NUL")
            latest = WatchlistReportGenerator(repo).latest_decisions(limit=5)

        self.assertIn("PM score", dossier)
        self.assertIn("# Latest Decisions Report", latest.markdown)

    def test_report_output_files_are_created(self) -> None:
        run_dir = self.write_complete_run("OUT", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "reports" / "company_dossiers" / "OUT.md"

        exit_code = company_reports_cli_main(
            ["dossier", "--db", str(self.db), "--ticker", "OUT", "--out", str(out)]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(out.exists())
        self.assertIn("Company Dossier: OUT - OUT Corp", out.read_text(encoding="utf-8"))

    def test_report_csv_export_writes_expected_headers(self) -> None:
        run_dir = self.write_complete_run("EXP", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "reports" / "watchlists" / "latest.md"
        csv_out = self.root / "reports" / "exports" / "latest.csv"

        exit_code = company_reports_cli_main(
            [
                "latest-decisions",
                "--db",
                str(self.db),
                "--limit",
                "10",
                "--out",
                str(out),
                "--csv-out",
                str(csv_out),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(out.exists())
        self.assertTrue(csv_out.exists())
        self.assertIn("ticker,company_name,market,action,rating", csv_out.read_text(encoding="utf-8"))

    def test_refresh_score_calculation(self) -> None:
        row = {
            "latest_run_date": "2026-01-01T00:00:00",
            "has_pm_decision": 1,
            "has_market_snapshot": 1,
            "has_chokepoint_assessment": 1,
            "evidence_count": 10,
            "facts_count": 3,
            "warning_count": 0,
            "chokepoint_score": 9,
            "pm_score": 7.5,
            "confidence": 5,
            "evidence_level": "primary_supported",
            "action": "watchlist",
        }
        result = score_refresh_candidate(row, as_of=datetime(2026, 1, 20, tzinfo=timezone.utc))

        self.assertGreaterEqual(result.score, 63)
        self.assertIn("stale_gt_14d", result.reason_codes)
        self.assertIn("high_chokepoint_score", result.reason_codes)
        self.assertIn("high_pm_score", result.reason_codes)

    def test_refresh_queue_classification(self) -> None:
        self.write_minimal_run("QUE", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            plan = RefreshPlanner(repo, as_of=datetime(2026, 2, 15, tzinfo=timezone.utc)).build_plan()

        candidate = [row for row in plan.candidates if row.ticker == "QUE"][0]
        self.assertEqual(candidate.queue, "urgent_refresh")
        self.assertIn("missing_market_snapshot", candidate.reason_codes)

    def test_refresh_stale_date_handling(self) -> None:
        self.write_complete_run("OLD", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 2, 15, tzinfo=timezone.utc)).explain("OLD")

        self.assertIsNotNone(candidate)
        self.assertIn("stale_gt_30d", candidate.reason_codes)

    def test_refresh_missing_artifact_handling(self) -> None:
        self.write_minimal_run("MIS", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc)).explain("MIS")

        self.assertIn("missing_market_snapshot", candidate.reason_codes)
        self.assertIn("no_evidence_items", candidate.reason_codes)
        self.assertIn("no_facts", candidate.reason_codes)

    def test_refresh_zero_evidence_and_facts_handling(self) -> None:
        self.write_minimal_run("ZER", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc)).explain("ZER")

        self.assertEqual(candidate.evidence_count, 0)
        self.assertEqual(candidate.fact_count, 0)

    def test_refresh_high_chokepoint_low_confidence(self) -> None:
        run_dir = self.write_complete_run("HCL", "20260101", "010203", chokepoint_score=9, confidence=1)
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc)).explain("HCL")

        self.assertIn("high_chokepoint_low_confidence", candidate.reason_codes)
        self.assertEqual(candidate.queue, "urgent_refresh")

    def test_refresh_high_chokepoint_low_evidence(self) -> None:
        self.write_minimal_run("HLE", "20260101", "010203", chokepoint_score=9, confidence=5)
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc)).explain("HLE")

        self.assertIn("high_chokepoint_low_evidence", candidate.reason_codes)
        self.assertEqual(candidate.queue, "urgent_refresh")

    def test_refresh_action_rating_change_detection(self) -> None:
        self.write_complete_run("ARC", "20260101", "010203", action="watchlist", rating="B")
        self.write_complete_run("ARC", "20260201", "010203", action="buy", rating="A")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 2, 5, tzinfo=timezone.utc)).explain("ARC")

        self.assertIn("action_changed", candidate.reason_codes)
        self.assertIn("rating_changed", candidate.reason_codes)

    def test_refresh_score_change_detection(self) -> None:
        self.write_complete_run("SCD", "20260101", "010203", pm_score=4, chokepoint_score=5)
        self.write_complete_run("SCD", "20260201", "010203", pm_score=7, chokepoint_score=8)
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 2, 5, tzinfo=timezone.utc)).explain("SCD")

        self.assertIn("pm_score_changed", candidate.reason_codes)
        self.assertIn("chokepoint_score_changed", candidate.reason_codes)

    def test_refresh_markdown_and_csv_output_creation(self) -> None:
        run_dir = self.write_complete_run("RFO", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "reports" / "refresh" / "refresh_plan.md"
        csv_out = self.root / "reports" / "refresh" / "refresh_queue.csv"

        exit_code = company_refresh_cli_main(
            ["plan", "--db", str(self.db), "--out", str(out), "--csv", str(csv_out)]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("# Company Refresh Plan", out.read_text(encoding="utf-8"))
        self.assertIn("priority_rank,ticker,company,market,queue", csv_out.read_text(encoding="utf-8"))

    def test_refresh_explain_command_data_generation(self) -> None:
        run_dir = self.write_complete_run("EXP2", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            text = RefreshPlanner(repo, as_of=datetime(2026, 1, 20, tzinfo=timezone.utc)).render_explain_text(
                RefreshPlanner(repo, as_of=datetime(2026, 1, 20, tzinfo=timezone.utc)).explain("EXP2"),
                "EXP2",
            )

        self.assertIn("Ticker: EXP2", text)
        self.assertIn("Refresh score:", text)
        self.assertIn("Suggested manual command:", text)

    def test_refresh_null_numeric_fields_do_not_crash(self) -> None:
        run_dir = self.write_complete_run(
            "RNU",
            "20260101",
            "010203",
            pm_score=None,
            chokepoint_score=None,
            confidence=None,
        )
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            candidate = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc)).explain("RNU")

        self.assertIsNotNone(candidate)
        self.assertIn("confidence_missing", candidate.reason_codes)

    def test_approval_packet_generation(self) -> None:
        urgent = self.write_minimal_run("APU", "20260101", "010203")
        high = self.write_complete_run(
            "APH",
            "20260101",
            "010204",
            action="buy",
            pm_score=7,
            chokepoint_score=6,
            confidence=5,
        )
        self.write_research_log([urgent, high])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 2, 15, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(ApprovalPacketOptions(limit=10))

        self.assertIn("# Research Refresh Approval Packet", result.markdown)
        self.assertIn("## 2. Proposed Refresh Queue", result.markdown)
        self.assertIn("## 4. Company Review Cards", result.markdown)
        self.assertGreaterEqual(len(result.selected_candidates), 2)

    def test_approval_manifest_generation(self) -> None:
        self.write_minimal_run("MAN", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build()

        self.assertEqual(list(result.manifest_rows[0]), MANIFEST_FIELDS)
        self.assertEqual(result.manifest_rows[0]["approved"], "")
        self.assertIn("suggested_manual_command", result.manifest_rows[0])

    def test_approval_command_bundle_generation(self) -> None:
        self.write_minimal_run("CMD", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build()

        self.assertIn("DO NOT RUN AUTOMATICALLY", result.command_bundle)
        self.assertIn("template only", result.command_bundle)
        self.assertIn("python ai_pm_agent.py single --ticker CMD", result.command_bundle)

    def test_approval_queue_filtering(self) -> None:
        self.write_minimal_run("AQF", "20260101", "010203")
        high = self.write_complete_run(
            "AHI",
            "20260101",
            "010204",
            action="buy",
            pm_score=7,
            chokepoint_score=6,
            confidence=5,
        )
        self.write_research_log([high])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 2, 15, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(
                ApprovalPacketOptions(queues=("high_priority",), limit=None)
            )

        self.assertEqual([candidate.queue for candidate in result.selected_candidates], ["high_priority"])
        self.assertEqual([candidate.ticker for candidate in result.selected_candidates], ["AHI"])

    def test_approval_min_score_filtering(self) -> None:
        self.write_minimal_run("AMS", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(
                ApprovalPacketOptions(min_score=80, limit=None)
            )

        self.assertTrue(result.selected_candidates)
        self.assertTrue(all(candidate.refresh_score >= 80 for candidate in result.selected_candidates))

    def test_approval_ticker_filtering(self) -> None:
        self.write_minimal_run("AT1", "20260101", "010203")
        self.write_minimal_run("AT2", "20260101", "010204")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(
                ApprovalPacketOptions(tickers=("AT2",), limit=None)
            )

        self.assertEqual([candidate.ticker for candidate in result.selected_candidates], ["AT2"])

    def test_approval_no_candidates_case(self) -> None:
        self.write_minimal_run("ANC", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(
                ApprovalPacketOptions(min_score=101, limit=None)
            )

        self.assertEqual(result.selected_candidates, ())
        self.assertIn("No candidates matched", result.markdown)
        self.assertIn("No command templates generated", result.command_bundle)

    def test_approval_missing_dossier_path_does_not_crash(self) -> None:
        self.write_minimal_run("NOD", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build()

        self.assertIn("existing dossier path", result.markdown)
        self.assertEqual(result.manifest_rows[0]["dossier_path"], "N/A")

    def test_approval_missing_numeric_fields_do_not_crash(self) -> None:
        run_dir = self.write_complete_run(
            "ANU",
            "20260101",
            "010203",
            pm_score=None,
            chokepoint_score=None,
            confidence=None,
        )
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()

        with CompanyResearchRepository(self.db) as repo:
            planner = RefreshPlanner(repo, as_of=datetime(2026, 1, 5, tzinfo=timezone.utc))
            result = ApprovalPacketGenerator(repo, planner=planner).build(
                ApprovalPacketOptions(queues=("no_refresh_needed",), exclude_no_refresh_needed=False, limit=None)
            )

        self.assertIn("ANU", result.markdown)
        self.assertIn("confidence_missing", result.markdown)

    def test_approval_cli_writes_outputs_and_headers(self) -> None:
        self.write_minimal_run("AWR", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "reports" / "approval" / "packet.md"
        manifest = self.root / "reports" / "approval" / "manifest.csv"
        commands = self.root / "reports" / "approval" / "commands.txt"

        exit_code = company_approval_cli_main(
            [
                "build",
                "--db",
                str(self.db),
                "--out",
                str(out),
                "--manifest",
                str(manifest),
                "--commands-out",
                str(commands),
                "--limit",
                "5",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(out.exists())
        self.assertTrue(manifest.exists())
        self.assertTrue(commands.exists())
        self.assertIn("# Research Refresh Approval Packet", out.read_text(encoding="utf-8"))
        self.assertIn(",".join(MANIFEST_FIELDS), manifest.read_text(encoding="utf-8"))
        self.assertIn("DO NOT RUN AUTOMATICALLY", commands.read_text(encoding="utf-8"))

    def test_approval_explain_packet_command(self) -> None:
        self.write_minimal_run("AEX", "20260101", "010203")
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        out = self.root / "reports" / "approval" / "packet.md"
        manifest = self.root / "reports" / "approval" / "manifest.csv"

        company_approval_cli_main(
            ["build", "--db", str(self.db), "--out", str(out), "--manifest", str(manifest), "--limit", "5"]
        )

        exit_code = company_approval_cli_main(
            ["explain-packet", "--db", str(self.db), "--manifest", str(manifest)]
        )

        self.assertEqual(exit_code, 0)

    def test_approval_approved_value_parsing(self) -> None:
        for value in ["true", "yes", "y", "1", "approve", "approved", "x", " YES "]:
            parsed = parse_approved_value(value)
            self.assertTrue(parsed.approved)
            self.assertFalse(parsed.ambiguous)

        for value in ["", "false", "no", "n", "0"]:
            parsed = parse_approved_value(value)
            self.assertFalse(parsed.approved)
            self.assertFalse(parsed.ambiguous)

    def test_approval_ambiguous_value_parsing(self) -> None:
        parsed = parse_approved_value("maybe")

        self.assertFalse(parsed.approved)
        self.assertTrue(parsed.ambiguous)
        self.assertIn("ambiguous_approved_value", parsed.warning)

    def test_approval_validate_valid_approved_row(self) -> None:
        run_dir = self.write_complete_run("VLD", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "approval_manifest.csv"
        self.write_approval_manifest(manifest, [self.approval_row("VLD", approved="yes", score="82")])

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertEqual(len(result.valid_approved_rows), 1)
        self.assertEqual(result.valid_approved_rows[0].status, "valid_approved")

    def test_approval_reject_missing_ticker(self) -> None:
        run_dir = self.write_complete_run("MTK", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "missing_ticker.csv"
        self.write_approval_manifest(manifest, [self.approval_row("", approved="yes")])

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertEqual(result.invalid_approved_rows[0].status, "invalid_approved")
        self.assertIn("missing_ticker", result.invalid_approved_rows[0].errors)

    def test_approval_warn_company_mismatch(self) -> None:
        run_dir = self.write_complete_run("CMM", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "company_mismatch.csv"
        self.write_approval_manifest(
            manifest,
            [self.approval_row("CMM", approved="yes", company="Completely Different Name")],
        )

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertEqual(len(result.valid_approved_rows), 1)
        self.assertTrue(any("company_mismatch_db" in warning for warning in result.rows[0].warnings))

    def test_approval_reject_invalid_queue(self) -> None:
        run_dir = self.write_complete_run("IQU", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "invalid_queue.csv"
        self.write_approval_manifest(manifest, [self.approval_row("IQU", approved="yes", queue="run_now")])

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertIn("invalid_queue", result.invalid_approved_rows[0].errors)

    def test_approval_reject_refresh_score_outside_range(self) -> None:
        run_dir = self.write_complete_run("SCR2", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "bad_score.csv"
        self.write_approval_manifest(manifest, [self.approval_row("SCR2", approved="yes", score="101")])

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertIn("refresh_score_outside_0_100", result.invalid_approved_rows[0].errors)

    def test_approval_reject_dangerous_shell_operators(self) -> None:
        run_dir = self.write_complete_run("DNG", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "dangerous.csv"
        command = 'python ai_pm_agent.py single --ticker DNG --name "DNG Corp" && del important.txt'
        self.write_approval_manifest(
            manifest,
            [self.approval_row("DNG", approved="yes", command=command)],
        )

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertTrue(dangerous_command_patterns(command))
        self.assertTrue(any("dangerous_command_pattern" in error for error in result.invalid_approved_rows[0].errors))

    def test_approval_safe_quoted_ampersand_not_rejected(self) -> None:
        command = 'python ai_pm_agent.py single --ticker ABC --name "A&B Corp" --market "US"'

        self.assertEqual(dangerous_command_patterns(command), [])

    def test_approval_validation_outputs_are_created(self) -> None:
        run_dir = self.write_complete_run("AVO", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "reports" / "approval" / "approval_manifest.csv"
        out = self.root / "reports" / "approval" / "approval_validation.md"
        csv_out = self.root / "reports" / "approval" / "approval_validation.csv"
        self.write_approval_manifest(manifest, [self.approval_row("AVO", approved="yes")])

        exit_code = company_approval_cli_main(
            ["validate", "--db", str(self.db), "--manifest", str(manifest), "--out", str(out), "--csv", str(csv_out)]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("# Approval Manifest Validation Report", out.read_text(encoding="utf-8"))
        self.assertIn("validation_status", csv_out.read_text(encoding="utf-8"))

    def test_approval_extract_outputs_are_created(self) -> None:
        run_dir = self.write_complete_run("AEO", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "reports" / "approval" / "approval_manifest.csv"
        commands = self.root / "reports" / "approval" / "approved_commands.txt"
        validated = self.root / "reports" / "approval" / "approved_manifest_validated.csv"
        validation = self.root / "reports" / "approval" / "approval_validation.md"
        self.write_approval_manifest(manifest, [self.approval_row("AEO", approved="x")])

        exit_code = company_approval_cli_main(
            [
                "extract-approved",
                "--db",
                str(self.db),
                "--manifest",
                str(manifest),
                "--commands-out",
                str(commands),
                "--manifest-out",
                str(validated),
                "--validation-out",
                str(validation),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("DO NOT RUN AUTOMATICALLY", commands.read_text(encoding="utf-8"))
        self.assertIn("rank=1 ticker=AEO", commands.read_text(encoding="utf-8"))
        self.assertIn("valid_approved", validated.read_text(encoding="utf-8"))
        self.assertTrue(validation.exists())

    def test_approval_dry_run_output_is_created_without_execution(self) -> None:
        run_dir = self.write_complete_run("DRY", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "reports" / "approval" / "approval_manifest.csv"
        out = self.root / "reports" / "approval" / "approved_dry_run.md"
        self.write_approval_manifest(manifest, [self.approval_row("DRY", approved="approved")])

        exit_code = company_approval_cli_main(
            ["dry-run-approved", "--db", str(self.db), "--manifest", str(manifest), "--out", str(out)]
        )

        self.assertEqual(exit_code, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("# Approved Commands Dry Run", text)
        self.assertIn("No commands executed.", text)
        self.assertIn("Commands That Would Be Included", text)

    def test_approval_empty_manifest_behavior(self) -> None:
        run_dir = self.write_complete_run("EMP2", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "empty_manifest.csv"
        self.write_approval_manifest(manifest, [])

        with CompanyResearchRepository(self.db) as repo:
            result = ApprovalManifestValidator(repo).validate(manifest)

        self.assertEqual(result.total_rows, 0)
        self.assertEqual(len(result.valid_approved_rows), 0)

    def test_approval_no_approved_rows_behavior(self) -> None:
        run_dir = self.write_complete_run("NAP", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "no_approved.csv"
        self.write_approval_manifest(manifest, [self.approval_row("NAP", approved="")])
        commands = self.root / "approved_commands.txt"
        validated = self.root / "approved_manifest_validated.csv"
        validation = self.root / "approval_validation.md"

        exit_code = company_approval_cli_main(
            [
                "extract-approved",
                "--db",
                str(self.db),
                "--manifest",
                str(manifest),
                "--commands-out",
                str(commands),
                "--manifest-out",
                str(validated),
                "--validation-out",
                str(validation),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No valid approved commands were found.", commands.read_text(encoding="utf-8"))
        self.assertIn("not_approved", validated.read_text(encoding="utf-8"))

    def test_runbook_with_zero_approved_rows(self) -> None:
        run_dir = self.write_complete_run("RB0", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "reports" / "approval" / "approved_manifest_validated.csv"
        commands = self.root / "reports" / "approval" / "approved_commands.txt"
        out = self.root / "reports" / "approval" / "manual_runbook.md"
        csv_out = self.root / "reports" / "approval" / "manual_runbook_steps.csv"
        self.write_validated_manifest(manifest, [self.validated_row("RB0", status="not_approved")])
        commands.write_text("DO NOT RUN AUTOMATICALLY.\nNo valid approved commands were found.\n", encoding="utf-8")

        exit_code = company_approval_cli_main(
            [
                "build-runbook",
                "--db",
                str(self.db),
                "--validated-manifest",
                str(manifest),
                "--commands",
                str(commands),
                "--out",
                str(out),
                "--csv",
                str(csv_out),
            ]
        )

        self.assertEqual(exit_code, 0)
        markdown = out.read_text(encoding="utf-8")
        self.assertIn("# Manual Research Refresh Runbook", markdown)
        self.assertIn("No commands are approved for execution", markdown)
        self.assertIn("This runbook does not execute commands.", markdown)
        self.assertEqual(csv_out.read_text(encoding="utf-8").strip(), ",".join(RUNBOOK_CSV_FIELDS))

    def test_runbook_with_valid_approved_rows(self) -> None:
        run_dir = self.write_complete_run("RB1", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "approved_manifest_validated.csv"
        commands = self.root / "approved_commands.txt"
        self.write_validated_manifest(manifest, [self.validated_row("RB1", status="valid_approved")])
        commands.write_text("# rank=1 ticker=RB1\npython ai_pm_agent.py single --ticker RB1\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        self.assertEqual(len(result.valid_approved_rows), 1)
        self.assertEqual(len(result.batches), 1)
        self.assertIn("## 4. Execution Batches", result.markdown)
        self.assertIn("python ai_pm_agent.py single --ticker RB1", result.markdown)

    def test_runbook_default_batch_grouping(self) -> None:
        rows = []
        run_dirs = []
        for index in range(6):
            ticker = f"BD{index}"
            run_dirs.append(self.write_complete_run(ticker, "20260101", f"01020{index}"))
            rows.append(self.validated_row(ticker, status="valid_approved", rank=str(index + 1)))
        self.write_research_log(run_dirs)
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "default_batches.csv"
        commands = self.root / "commands.txt"
        self.write_validated_manifest(manifest, rows)
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        self.assertEqual(len(result.batches), 2)
        self.assertEqual([len(batch.rows) for batch in result.batches], [5, 1])

    def test_runbook_custom_batch_grouping(self) -> None:
        rows = []
        run_dirs = []
        for index in range(5):
            ticker = f"BC{index}"
            run_dirs.append(self.write_complete_run(ticker, "20260101", f"01021{index}"))
            rows.append(self.validated_row(ticker, status="valid_approved", rank=str(index + 1)))
        self.write_research_log(run_dirs)
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "custom_batches.csv"
        commands = self.root / "commands.txt"
        self.write_validated_manifest(manifest, rows)
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands, batch_size=2)

        self.assertEqual(len(result.batches), 3)
        self.assertEqual([len(batch.rows) for batch in result.batches], [2, 2, 1])

    def test_runbook_excluded_rows_section(self) -> None:
        run_dir = self.write_complete_run("EXC", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "excluded.csv"
        commands = self.root / "commands.txt"
        self.write_validated_manifest(
            manifest,
            [
                self.validated_row("EXC", status="invalid_approved", errors="invalid_queue"),
                self.validated_row("EX2", status="ambiguous_approval", warnings="ambiguous_approved_value=maybe"),
            ],
        )
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        self.assertIn("## 6. Excluded Rows", result.markdown)
        self.assertIn("invalid_queue", result.markdown)
        self.assertIn("ambiguous_approval", result.markdown)

    def test_runbook_csv_headers_are_written(self) -> None:
        run_dir = self.write_complete_run("RCH", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "headers.csv"
        commands = self.root / "commands.txt"
        out = self.root / "runbook.md"
        csv_out = self.root / "steps.csv"
        self.write_validated_manifest(manifest, [])
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            ManualRunbookGenerator(repo).write(manifest, commands, out, csv_out)

        self.assertIn(",".join(RUNBOOK_CSV_FIELDS), csv_out.read_text(encoding="utf-8"))

    def test_runbook_command_text_included_but_not_executed(self) -> None:
        run_dir = self.write_complete_run("RCE", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "command_text.csv"
        commands = self.root / "commands.txt"
        command = 'python ai_pm_agent.py single --ticker RCE --name "RCE Corp" --market "US"'
        self.write_validated_manifest(
            manifest,
            [self.validated_row("RCE", status="valid_approved", command=command)],
        )
        commands.write_text(command + "\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        self.assertIn(command, result.markdown)
        self.assertFalse((self.root / "outputs" / "live_execution_marker").exists())

    def test_runbook_missing_approved_commands_file_handled(self) -> None:
        run_dir = self.write_complete_run("MAC", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "missing_commands.csv"
        missing_commands = self.root / "does_not_exist.txt"
        self.write_validated_manifest(manifest, [self.validated_row("MAC", status="valid_approved")])

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, missing_commands)

        self.assertIn("Approved commands file not found", result.markdown)
        self.assertEqual(len(result.valid_approved_rows), 1)

    def test_runbook_missing_optional_numeric_fields_do_not_crash(self) -> None:
        run_dir = self.write_complete_run("NON", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "optional_numeric.csv"
        commands = self.root / "commands.txt"
        row = self.validated_row("NON", status="valid_approved")
        row["pm_score"] = ""
        row["chokepoint_score"] = ""
        row["confidence"] = ""
        self.write_validated_manifest(manifest, [row])
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        self.assertIn("# Manual Research Refresh Runbook", result.markdown)
        self.assertEqual(len(result.csv_rows), 1)

    def test_runbook_markdown_contains_expected_headers(self) -> None:
        run_dir = self.write_complete_run("HDR", "20260101", "010203")
        self.write_research_log([run_dir])
        CompanyDbImporter(self.outputs, self.db).import_outputs()
        manifest = self.root / "headers_manifest.csv"
        commands = self.root / "commands.txt"
        self.write_validated_manifest(manifest, [self.validated_row("HDR", status="valid_approved")])
        commands.write_text("DO NOT RUN AUTOMATICALLY.\n", encoding="utf-8")

        with CompanyResearchRepository(self.db, read_only=True) as repo:
            result = ManualRunbookGenerator(repo).build(manifest, commands)

        for header in [
            "## 1. Executive Summary",
            "## 2. Current Approval Status",
            "## 3. Pre-Run Safety Checklist",
            "## 4. Execution Batches",
            "## 5. Post-Run Verification Checklist",
            "## 6. Excluded Rows",
            "## 7. Limitations",
        ]:
            self.assertIn(header, result.markdown)

    def test_smoke_test_result_aggregation(self) -> None:
        steps = [
            company_db_smoke_test.StepResult("one", "check one", "passed", 0.1, "ok"),
            company_db_smoke_test.StepResult("two", "check two", "failed", 0.2, "bad"),
            company_db_smoke_test.StepResult("three", "check three", "skipped", 0.0, ""),
        ]

        summary = company_db_smoke_test.summarize_steps(steps, total_elapsed_seconds=1.5)

        self.assertEqual(summary.status, "failed")
        self.assertEqual(summary.total_steps, 3)
        self.assertEqual(summary.passed_steps, 1)
        self.assertEqual(summary.failed_steps, 1)
        self.assertEqual(summary.skipped_steps, 1)

    def test_smoke_test_file_validation(self) -> None:
        good = self.root / "reports" / "workflow" / "good.md"
        empty = self.root / "reports" / "workflow" / "empty.md"
        good.parent.mkdir(parents=True)
        good.write_text("content", encoding="utf-8")
        empty.write_text("", encoding="utf-8")

        results = company_db_smoke_test.validate_expected_outputs(
            self.root,
            [
                "reports/workflow/good.md",
                "reports/workflow/empty.md",
                "reports/workflow/missing.md",
            ],
        )

        statuses = {result.output: result.status for result in results}
        self.assertEqual(statuses["reports/workflow/good.md"], "passed")
        self.assertEqual(statuses["reports/workflow/empty.md"], "failed")
        self.assertEqual(statuses["reports/workflow/missing.md"], "failed")

    def test_smoke_test_blocks_ai_pm_agent_command(self) -> None:
        self.assertTrue(company_db_smoke_test.command_targets_ai_pm_agent(["python", "ai_pm_agent.py", "single"]))
        self.assertFalse(
            company_db_smoke_test.command_targets_ai_pm_agent(["python", "scripts/company_db_import.py", "stats"])
        )

    def approval_row(
        self,
        ticker: str,
        approved: str = "",
        company: str | None = None,
        queue: str = "urgent_refresh",
        score: str = "80",
        command: str | None = None,
    ) -> dict[str, str]:
        company_name = company if company is not None else f"{ticker} Corp"
        command_text = command or (
            f'python ai_pm_agent.py single --ticker {ticker} --name "{company_name}" --market "US" '
            "# template only; do not execute without approval"
        )
        values = {
            "approved": approved,
            "rank": "1",
            "ticker": ticker,
            "company": company_name,
            "market": "US",
            "queue": queue,
            "refresh_score": score,
            "latest_action": "watchlist",
            "latest_rating": "watch",
            "pm_score": "7",
            "chokepoint_score": "8",
            "confidence": "3",
            "latest_run_date": "2026-01-01T00:00:00",
            "warning_count": "0",
            "evidence_count": "1",
            "fact_count": "1",
            "reason_codes": "stale_gt_14d,high_pm_score",
            "suggested_manual_command": command_text,
            "dossier_path": "N/A",
            "artifact_path": str(self.outputs / "dummy"),
            "notes": "",
        }
        return {field: values.get(field, "") for field in MANIFEST_FIELDS}

    def write_approval_manifest(self, path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})

    def validated_row(
        self,
        ticker: str,
        status: str = "valid_approved",
        rank: str = "1",
        command: str | None = None,
        errors: str = "",
        warnings: str = "",
    ) -> dict[str, str]:
        row = self.approval_row(ticker, approved="x")
        row.update(
            {
                "validation_status": status,
                "validation_errors": errors,
                "validation_warnings": warnings,
                "rank": rank,
                "suggested_manual_command": command or row["suggested_manual_command"],
            }
        )
        return {field: row.get(field, "") for field in VALIDATED_MANIFEST_FIELDS}

    def write_validated_manifest(self, path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=VALIDATED_MANIFEST_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in VALIDATED_MANIFEST_FIELDS})

    def write_complete_run(
        self,
        ticker: str,
        date_text: str,
        time_text: str,
        action: str = "watchlist",
        rating: str = "B",
        pm_score: float | None = 72,
        chokepoint_score: float | None = 82,
        confidence: float | None = 0.7,
    ) -> Path:
        run_dir = self.run_dir(ticker, date_text, time_text)
        run_dir.mkdir(parents=True)
        pm_decision = {
            "ticker": ticker,
            "company_name": f"{ticker} Corp",
            "rating": rating,
            "action": action,
            "suggested_position_pct": 1.5,
            "confidence_score": confidence,
            "risk_score": 0.4,
            "evidence_quality_score": 0.8,
            "weighted_investment_score": pm_score,
            "chokepoint_adjusted_score": 75,
            "thesis_summary": "Test thesis.",
            "final_pm_judgment": "Test judgment.",
            "valuation_view": "fair",
            "valuation_is_justified": True,
            "chokepoint_score": chokepoint_score,
            "indispensability_score": 80,
            "scarcity_score": 78,
            "customer_validation_score": 76,
            "nvidia_signal_score": 70,
            "substitution_risk_score": 20,
            "timing_risk_score": 30,
            "market_awareness_score": 50,
            "valuation_risk_score": 40,
            "serenity_thesis_quality": "medium",
            "chokepoint_evidence_level": "credible",
            "deep_research_priority": "normal",
            "scout_recommendation": "monitor",
            "chokepoint_overlay_applied": False,
            "chokepoint_overlay_reason": "none",
        }
        market_snapshot = {
            "ticker": ticker,
            "financial_ticker": ticker,
            "short_name": f"{ticker} Corp",
            "long_name": f"{ticker} Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
            "country": "US",
            "currency": "USD",
            "financial_currency": "USD",
            "latest_price": 100.0,
            "market_cap": 1000000,
            "enterprise_value": 900000,
            "trailing_pe": 20,
            "forward_pe": 18,
            "price_to_sales": 4,
            "price_to_book": 5,
            "ev_to_revenue": 3,
            "ev_to_ebitda": 12,
            "one_year_return": 0.1,
            "volatility_1y": 0.2,
            "max_drawdown_2y": -0.3,
            "trend_label": "up",
            "market_data_reliability": "ok",
        }
        (run_dir / "pm_decision.json").write_text(json.dumps(pm_decision), encoding="utf-8")
        (run_dir / "market_snapshot.json").write_text(json.dumps(market_snapshot), encoding="utf-8")
        (run_dir / "quality_report.md").write_text("# Quality\nOK\n", encoding="utf-8")
        (run_dir / "market_snapshot.md").write_text("# Market\nOK\n", encoding="utf-8")
        (run_dir / "evidence_context.md").write_text(
            "\n".join(
                [
                    "- Source: tavily",
                    "  Query Type: customer_validation",
                    "  Expected Tier: primary",
                    "  Evidence Tier: primary",
                    "  Source Type: filing",
                    "  Source Domain: example.com",
                    "  Title: Evidence Title",
                    "  URL: https://example.com/evidence",
                    "  Snippet: Evidence snippet.",
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "fact_cache_report_before.json").write_text("{}", encoding="utf-8")
        (run_dir / "fact_cache_report_before.md").write_text("# Before\n", encoding="utf-8")
        (run_dir / "fact_cache_report_after.json").write_text("{}", encoding="utf-8")
        (run_dir / "fact_cache_report_after.md").write_text("# After\n", encoding="utf-8")
        fact = {
            "ticker": ticker,
            "company_name": f"{ticker} Corp",
            "fact": "Important fact.",
            "fact_category": "customer",
            "source_url": "https://example.com/fact",
            "source_domain": "example.com",
            "confidence": 0.9,
            "query_type": "customer_validation",
            "provider": "test",
        }
        (run_dir / "cached_facts_used.json").write_text(json.dumps([fact]), encoding="utf-8")
        (run_dir / "fresh_facts.json").write_text(json.dumps([fact]), encoding="utf-8")
        return run_dir

    def write_minimal_run(
        self,
        ticker: str,
        date_text: str,
        time_text: str,
        chokepoint_score: float | None = None,
        confidence: float | None = None,
    ) -> Path:
        run_dir = self.run_dir(ticker, date_text, time_text)
        run_dir.mkdir(parents=True)
        pm_decision = {
            "ticker": ticker,
            "company_name": f"{ticker} Corp",
            "action": "watchlist",
            "chokepoint_score": chokepoint_score,
            "confidence_score": confidence,
        }
        (run_dir / "pm_decision.json").write_text(json.dumps(pm_decision), encoding="utf-8")
        return run_dir

    def write_research_log(self, run_dirs: list[Path]) -> None:
        lines = [
            "created_at,ticker,company_name,theme,market,rating,action,output_dir,pm_decision_json",
        ]
        for run_dir in run_dirs:
            ticker = run_dir.name.split("_", 1)[0]
            rel_run = run_dir.relative_to(self.outputs.parent)
            rel_pm = (run_dir / "pm_decision.json").relative_to(self.outputs.parent)
            lines.append(
                f"2026-01-01T00:00:00,{ticker},{ticker} Corp,AI,US,B,watchlist,{rel_run},{rel_pm}"
            )
        (self.outputs / "research_log.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_dir(self, ticker: str, date_text: str, time_text: str) -> Path:
        return self.outputs / date_text / f"{ticker}_{date_text}_{time_text}"


if __name__ == "__main__":
    unittest.main()

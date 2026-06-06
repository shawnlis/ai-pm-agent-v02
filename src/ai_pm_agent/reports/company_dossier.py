"""Single-company offline dossier generation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.reports.markdown import (
    bullet_list,
    compact,
    display,
    field_table,
    generated_at,
    row_to_dict,
    section,
    table,
)


MARKET_FIELDS = [
    "short_name",
    "long_name",
    "sector",
    "industry",
    "country",
    "currency",
    "financial_currency",
    "latest_price",
    "market_cap",
    "enterprise_value",
    "trailing_pe",
    "forward_pe",
    "price_to_sales",
    "price_to_book",
    "ev_to_revenue",
    "ev_to_ebitda",
    "one_year_return",
    "volatility_1y",
    "max_drawdown_2y",
    "trend_label",
    "market_data_reliability",
    "financial_statement_reliability",
    "price_data_reliability_from_fetch",
]


class CompanyDossierGenerator:
    """Build deterministic Markdown dossiers from existing SQLite rows."""

    def __init__(self, repo: CompanyResearchRepository):
        self.repo = repo

    def generate(self, ticker: str) -> str:
        latest = self.repo.get_latest_report_row_for_ticker(ticker)
        if latest is None:
            raise ValueError(f"No company DB rows found for ticker: {ticker}")

        run_id = latest["run_id"]
        pm = self.repo.get_pm_decision_for_run(run_id)
        market = self.repo.get_market_snapshot_for_run(run_id)
        chokepoint = self.repo.get_chokepoint_assessment_for_run(run_id)
        evidence = self.repo.list_evidence_for_run(run_id, limit=12)
        facts = self.repo.list_facts_for_run(run_id, limit=12)
        warnings = self.repo.list_warnings_for_run(run_id, limit=200)
        history = self.repo.compare_ticker_history(latest["ticker"], limit=100)

        title = f"# Company Dossier: {display(latest['ticker'])} - {display(latest['company_name'])}"
        sections = [
            f"Generated: {generated_at()}\n\nDatabase: `{self.repo.db_path}`",
            section("1. Latest Decision Summary", self._latest_summary(latest)),
            section("2. Chokepoint Assessment", self._chokepoint_section(chokepoint, pm)),
            section("3. Market / Valuation Snapshot", self._market_section(market)),
            section("4. Evidence Summary", self._evidence_section(evidence, latest)),
            section("5. Facts Summary", self._facts_section(facts, latest)),
            section("6. Historical Decision Timeline", self._history_section(history)),
            section("7. Data Quality / Import Warnings", self._warnings_section(warnings, latest)),
            section(
                "8. Analyst Notes / Next Refresh Checklist",
                self._checklist(latest, warnings),
            ),
        ]
        return "\n\n".join([title, *sections]).strip() + "\n"

    def _latest_summary(self, latest: Any) -> str:
        rows = [
            ("Ticker", latest["ticker"]),
            ("Company", latest["company_name"]),
            ("Market", latest["market"]),
            ("Latest action", latest["action"]),
            ("Latest rating", latest["rating"]),
            ("PM score", latest["pm_score"]),
            ("Chokepoint score", latest["chokepoint_score"]),
            ("Confidence", latest["confidence"]),
            ("Suggested position", latest["suggested_position_pct"]),
            ("Latest run date", latest["latest_run_date"]),
            ("Artifact path", latest["artifact_dir"]),
        ]
        return field_table(rows)

    def _chokepoint_section(self, chokepoint: Any, pm: Any) -> str:
        cp = row_to_dict(chokepoint)
        pm_row = row_to_dict(pm)
        rows = [
            ("Chokepoint score", cp.get("chokepoint_score")),
            ("Evidence level", cp.get("evidence_level")),
            ("Indispensability score", cp.get("indispensability_score")),
            ("Scarcity score", cp.get("scarcity_score")),
            ("Customer validation score", cp.get("customer_validation_score")),
            ("NVIDIA signal score", cp.get("nvidia_signal_score")),
            ("Substitution risk score", cp.get("substitution_risk_score")),
            ("Timing risk score", cp.get("timing_risk_score")),
            ("Market awareness score", cp.get("market_awareness_score")),
            ("Valuation risk score", cp.get("valuation_risk_score")),
            ("Serenity thesis quality", cp.get("serenity_thesis_quality")),
            ("Scout recommendation", cp.get("scout_recommendation")),
            ("Overlay applied", cp.get("overlay_applied")),
            ("Overlay reason", cp.get("overlay_reason")),
            ("Overlay warnings", cp.get("overlay_warnings_json")),
            ("Thesis summary", pm_row.get("thesis_summary")),
            ("Final PM judgment", pm_row.get("final_pm_judgment")),
            ("Valuation view", pm_row.get("valuation_view")),
        ]
        return field_table(rows)

    def _market_section(self, market: Any) -> str:
        if market is None:
            return "No market_snapshot row is indexed for this latest run."
        market_row = row_to_dict(market)
        rows = [(field, market_row.get(field)) for field in MARKET_FIELDS]
        raw_summary = self._raw_json_summary(market_row.get("raw_json"))
        return field_table(rows + [("Raw field availability", raw_summary)])

    def _evidence_section(self, evidence: list[Any], latest: Any) -> str:
        evidence_count = int(latest["evidence_count"] or 0)
        if not evidence:
            return f"Evidence items indexed for latest run: {evidence_count}\n\nNo evidence_items are indexed for this run."
        tiers = Counter(display(row["evidence_tier"]) for row in evidence)
        dist = ", ".join(f"{tier}: {count}" for tier, count in sorted(tiers.items()))
        rows = [
            [
                row["evidence_tier"],
                row["source_type"],
                row["source_domain"],
                compact(row["title"], 80),
                row["url"],
            ]
            for row in evidence
        ]
        return (
            f"Evidence items indexed for latest run: {evidence_count}\n\n"
            f"Source-tier distribution in displayed rows: {dist}\n\n"
            + table(["Tier", "Type", "Domain", "Title", "URL"], rows)
        )

    def _facts_section(self, facts: list[Any], latest: Any) -> str:
        facts_count = int(latest["facts_count"] or 0)
        if not facts:
            return f"Facts indexed for latest run: {facts_count}\n\nNo facts are indexed for this run."
        rows = [
            [
                compact(row["fact"], 100),
                row["fact_category"],
                row["confidence"],
                row["source_domain"],
                row["source_url"],
            ]
            for row in facts
        ]
        return f"Facts indexed for latest run: {facts_count}\n\n" + table(
            ["Fact", "Category", "Confidence", "Domain", "URL"],
            rows,
        )

    def _history_section(self, history: list[Any]) -> str:
        if not history:
            return "No historical runs are indexed for this ticker."
        rows = [
            [
                row["latest_run_date"],
                row["action"],
                row["rating"],
                row["pm_score"],
                row["chokepoint_score"],
                row["suggested_position_pct"],
                row["artifact_dir"],
            ]
            for row in history
        ]
        return table(
            [
                "run_date",
                "action",
                "rating",
                "pm_score",
                "chokepoint_score",
                "suggested_position",
                "artifact_path",
            ],
            rows,
        )

    def _warnings_section(self, warnings: list[Any], latest: Any) -> str:
        warning_count = int(latest["warning_count"] or 0)
        flags = [
            f"warning_count: {warning_count}",
            f"evidence_count: {latest['evidence_count']}",
            f"facts_count: {latest['facts_count']}",
            f"has_market_snapshot: {latest['has_market_snapshot']}",
            f"has_pm_decision: {latest['has_pm_decision']}",
            f"has_chokepoint_assessment: {latest['has_chokepoint_assessment']}",
        ]
        if not warnings:
            return bullet_list(flags) + "\n\nNo import warnings are indexed for this latest run."
        type_counts = Counter(row["warning_type"] for row in warnings)
        missing = [
            row["message"].replace("Optional artifact is missing: ", "")
            for row in warnings
            if row["warning_type"] == "missing_optional_artifact"
        ]
        warning_rows = [[row["warning_type"], row["message"], row["artifact_path"]] for row in warnings[:20]]
        return (
            bullet_list(flags)
            + "\n\nWarning types: "
            + ", ".join(f"{key}: {value}" for key, value in sorted(type_counts.items()))
            + "\n\nMissing optional artifacts: "
            + (", ".join(sorted(set(missing))) if missing else "N/A")
            + "\n\n"
            + table(["Type", "Message", "Artifact path"], warning_rows)
        )

    def _checklist(self, latest: Any, warnings: list[Any]) -> str:
        items = []
        if self._is_stale(latest["latest_run_date"]):
            items.append("[ ] Rerun company if the latest run is stale.")
        if int(latest["evidence_count"] or 0) == 0:
            items.append("[ ] Rerun company if evidence_items are missing.")
        if int(latest["facts_count"] or 0) == 0:
            items.append("[ ] Rerun company if facts are missing.")
        if _num(latest["chokepoint_score"]) is not None and _num(latest["confidence"]) is not None:
            if _num(latest["chokepoint_score"]) >= 8 and _num(latest["confidence"]) <= 3:
                items.append("[ ] Review high chokepoint score with low confidence.")
        if _num(latest["pm_score"]) is not None and _num(latest["chokepoint_score"]) is not None:
            if abs(_num(latest["pm_score"]) - _num(latest["chokepoint_score"])) >= 3:
                items.append("[ ] Review divergence between PM score and chokepoint score.")
        if len(warnings) >= 5:
            items.append("[ ] Review high import warning count before relying on this dossier.")
        if int(latest["has_market_snapshot"] or 0) == 0:
            items.append("[ ] Rerun or inspect artifacts because the market snapshot is missing.")
        if not items:
            items.append("[ ] No automatic refresh flags from current indexed data.")
        return "\n".join(f"- {item}" for item in items)

    def _is_stale(self, value: Any, days: int = 30) -> bool:
        text = display(value)
        if text == "N/A":
            return True
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).days > days

    def _raw_json_summary(self, raw_json: Any) -> str:
        if not raw_json:
            return "N/A"
        try:
            obj = json.loads(raw_json)
        except (TypeError, json.JSONDecodeError):
            return "raw_json present but not parseable"
        if isinstance(obj, dict):
            populated = sum(1 for value in obj.values() if value not in (None, "", [], {}))
            return f"{populated} populated fields out of {len(obj)} raw fields"
        return f"raw_json type: {type(obj).__name__}"


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

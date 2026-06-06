"""Offline refresh-candidate planner built on the company DB query layer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ai_pm_agent.company_db.repository import CompanyResearchRepository, DecisionFilters
from ai_pm_agent.refresh.queues import QUEUE_ORDER, REASON_EXPLANATIONS
from ai_pm_agent.refresh.scoring import ScoreSignal, score_refresh_candidate
from ai_pm_agent.reports.markdown import bullet_list, generated_at, rows_to_dicts, table


CSV_FIELDS = [
    "priority_rank",
    "ticker",
    "company",
    "market",
    "queue",
    "refresh_score",
    "latest_action",
    "latest_rating",
    "pm_score",
    "chokepoint_score",
    "confidence",
    "latest_run_date",
    "warning_count",
    "evidence_count",
    "fact_count",
    "reason_codes",
    "suggested_manual_command",
    "artifact_path",
]


@dataclass(frozen=True)
class RefreshCandidate:
    priority_rank: int
    ticker: str
    company: str
    market: str
    queue: str
    refresh_score: int
    latest_action: str
    latest_rating: str
    pm_score: Any
    chokepoint_score: Any
    confidence: Any
    latest_run_date: str
    warning_count: int
    evidence_count: int
    fact_count: int
    reason_codes: tuple[str, ...]
    score_breakdown: tuple[ScoreSignal, ...]
    suggested_manual_command: str
    artifact_path: str

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "priority_rank": self.priority_rank,
            "ticker": self.ticker,
            "company": self.company,
            "market": self.market,
            "queue": self.queue,
            "refresh_score": self.refresh_score,
            "latest_action": self.latest_action,
            "latest_rating": self.latest_rating,
            "pm_score": self.pm_score,
            "chokepoint_score": self.chokepoint_score,
            "confidence": self.confidence,
            "latest_run_date": self.latest_run_date,
            "warning_count": self.warning_count,
            "evidence_count": self.evidence_count,
            "fact_count": self.fact_count,
            "reason_codes": ",".join(self.reason_codes),
            "suggested_manual_command": self.suggested_manual_command,
            "artifact_path": self.artifact_path,
        }


@dataclass(frozen=True)
class RefreshPlan:
    db_path: str
    generated_at: str
    companies_evaluated: int
    candidates: tuple[RefreshCandidate, ...]
    db_summary: dict[str, Any]

    @property
    def queue_counts(self) -> dict[str, int]:
        counter = Counter(candidate.queue for candidate in self.candidates)
        return {queue: counter.get(queue, 0) for queue in QUEUE_ORDER}

    @property
    def reason_counts(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for candidate in self.candidates:
            counter.update(candidate.reason_codes)
        return dict(sorted(counter.items()))


class RefreshPlanner:
    """Evaluate latest ticker rows and produce deterministic refresh queues."""

    def __init__(self, repo: CompanyResearchRepository, as_of: datetime | None = None):
        self.repo = repo
        self.as_of = as_of or datetime.now(timezone.utc)

    def build_plan(self) -> RefreshPlan:
        latest_rows = self.repo.filter_decisions(
            filters=DecisionFilters(),
            limit=100000,
            sort="latest_run_date",
            desc=True,
        )
        ranked = []
        for row in rows_to_dicts(latest_rows):
            previous = self._previous_row(row["ticker"])
            score = score_refresh_candidate(row, previous=previous, as_of=self.as_of)
            ranked.append(self._candidate_from_row(row, score))

        ranked.sort(
            key=lambda candidate: (
                QUEUE_ORDER.index(candidate.queue),
                -candidate.refresh_score,
                candidate.ticker,
            )
        )
        candidates = tuple(
            self._replace_rank(candidate, rank)
            for rank, candidate in enumerate(ranked, start=1)
        )
        return RefreshPlan(
            db_path=str(self.repo.db_path),
            generated_at=generated_at(),
            companies_evaluated=len(candidates),
            candidates=candidates,
            db_summary=self.repo.summarize_database(),
        )

    def explain(self, ticker: str) -> RefreshCandidate | None:
        ticker_norm = ticker.strip().upper()
        for candidate in self.build_plan().candidates:
            if candidate.ticker.upper() == ticker_norm:
                return candidate
        return None

    def render_plan_markdown(self, plan: RefreshPlan, include_all: bool = False) -> str:
        lines = [
            "# Company Refresh Plan",
            "",
            "## 1. Summary",
            "",
            bullet_list(
                [
                    f"Generated: {plan.generated_at}",
                    f"DB path: `{plan.db_path}`",
                    f"Companies evaluated: {plan.companies_evaluated}",
                    "Queue counts: " + _counts_text(plan.queue_counts),
                    "Highest priority tickers: "
                    + ", ".join(candidate.ticker for candidate in plan.candidates[:10]),
                    "Warning counts: " + _counts_text(plan.db_summary.get("warning_types", {})),
                ]
            ),
            "",
        ]
        queue_titles = {
            "urgent_refresh": "2. Urgent Refresh Queue",
            "high_priority": "3. High Priority Queue",
            "normal_refresh": "4. Normal Refresh Queue",
            "monitor_only": "5. Monitor Only",
        }
        for queue in QUEUE_ORDER[:-1]:
            if queue == "no_refresh_needed":
                continue
            queue_rows = [candidate for candidate in plan.candidates if candidate.queue == queue]
            limit = None if include_all or queue != "monitor_only" else 30
            displayed = queue_rows if limit is None else queue_rows[:limit]
            lines.extend(
                [
                    f"## {queue_titles[queue]}",
                    "",
                    _candidate_table(displayed),
                    "",
                ]
            )
            if limit is not None and len(queue_rows) > len(displayed):
                lines.append(f"Monitor-only rows hidden: {len(queue_rows) - len(displayed)}")
                lines.append("")

        no_refresh = [candidate for candidate in plan.candidates if candidate.queue == "no_refresh_needed"]
        lines.extend(
            [
                "## 6. No Refresh Needed",
                "",
                f"Count: {len(no_refresh)}",
                "",
                "## 7. Reason Code Summary",
                "",
                _reason_table(plan.reason_counts),
                "",
                "## 8. Suggested Manual Next Commands",
                "",
                self._manual_commands(plan),
                "",
                "## 9. Limitations",
                "",
                bullet_list(
                    [
                        "Offline planner only; no live data freshness check is performed.",
                        "Scoring is deterministic but heuristic.",
                        "Suggested commands are templates only and are not executed.",
                        "The user must approve any live rerun.",
                    ]
                ),
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def render_queue_markdown(self, plan: RefreshPlan, queue: str, include_all: bool = True) -> str:
        queue_rows = [candidate for candidate in plan.candidates if candidate.queue == queue]
        displayed = queue_rows if include_all else queue_rows[:30]
        return (
            f"# Refresh Queue: {queue}\n\n"
            + bullet_list(
                [
                    f"Generated: {plan.generated_at}",
                    f"DB path: `{plan.db_path}`",
                    f"Rows in queue: {len(queue_rows)}",
                    f"Rows displayed: {len(displayed)}",
                ]
            )
            + "\n\n"
            + _candidate_table(displayed)
            + "\n"
        )

    def render_explain_text(self, candidate: RefreshCandidate | None, ticker: str) -> str:
        if candidate is None:
            return f"Ticker: {ticker.upper()}\nNo refresh candidate found.\n"
        breakdown = "\n".join(
            f"* {signal.code}: +{signal.points}" for signal in candidate.score_breakdown
        )
        if not breakdown:
            breakdown = "* no_refresh_signals: +0"
        return f"""Ticker: {candidate.ticker}
Refresh score: {candidate.refresh_score}
Queue: {candidate.queue}

Score breakdown:

{breakdown}

Latest decision:

* action: {candidate.latest_action or 'N/A'}
* rating: {candidate.latest_rating or 'N/A'}
* pm_score: {candidate.pm_score if candidate.pm_score not in (None, '') else 'N/A'}
* chokepoint_score: {candidate.chokepoint_score if candidate.chokepoint_score not in (None, '') else 'N/A'}
* confidence: {candidate.confidence if candidate.confidence not in (None, '') else 'N/A'}
* latest_run_date: {candidate.latest_run_date or 'N/A'}

Suggested manual command:
{candidate.suggested_manual_command}
"""

    def _previous_row(self, ticker: str) -> dict[str, Any] | None:
        history = rows_to_dicts(self.repo.compare_ticker_history(ticker, limit=2))
        if len(history) < 2:
            return None
        return history[1]

    def _candidate_from_row(self, row: dict[str, Any], score: Any) -> RefreshCandidate:
        ticker = str(row.get("ticker") or "").upper()
        company = str(row.get("company_name") or ticker)
        market = str(row.get("market") or "")
        return RefreshCandidate(
            priority_rank=0,
            ticker=ticker,
            company=company,
            market=market,
            queue=score.queue,
            refresh_score=score.score,
            latest_action=str(row.get("action") or ""),
            latest_rating=str(row.get("rating") or ""),
            pm_score=row.get("pm_score"),
            chokepoint_score=row.get("chokepoint_score"),
            confidence=row.get("confidence"),
            latest_run_date=str(row.get("latest_run_date") or ""),
            warning_count=int(row.get("warning_count") or 0),
            evidence_count=int(row.get("evidence_count") or 0),
            fact_count=int(row.get("facts_count") or 0),
            reason_codes=tuple(score.reason_codes),
            score_breakdown=tuple(score.signals),
            suggested_manual_command=manual_command(ticker, company, market),
            artifact_path=str(row.get("artifact_dir") or ""),
        )

    def _replace_rank(self, candidate: RefreshCandidate, rank: int) -> RefreshCandidate:
        return RefreshCandidate(
            priority_rank=rank,
            ticker=candidate.ticker,
            company=candidate.company,
            market=candidate.market,
            queue=candidate.queue,
            refresh_score=candidate.refresh_score,
            latest_action=candidate.latest_action,
            latest_rating=candidate.latest_rating,
            pm_score=candidate.pm_score,
            chokepoint_score=candidate.chokepoint_score,
            confidence=candidate.confidence,
            latest_run_date=candidate.latest_run_date,
            warning_count=candidate.warning_count,
            evidence_count=candidate.evidence_count,
            fact_count=candidate.fact_count,
            reason_codes=candidate.reason_codes,
            score_breakdown=candidate.score_breakdown,
            suggested_manual_command=candidate.suggested_manual_command,
            artifact_path=candidate.artifact_path,
        )

    def _manual_commands(self, plan: RefreshPlan) -> str:
        rows = [
            candidate
            for candidate in plan.candidates
            if candidate.queue in {"urgent_refresh", "high_priority"}
        ][:30]
        if not rows:
            return "No urgent or high-priority manual command templates."
        return "\n".join(
            f"- {candidate.ticker}: `{candidate.suggested_manual_command}`"
            for candidate in rows
        )


def manual_command(ticker: str, company: str, market: str) -> str:
    parts = ["python", "ai_pm_agent.py", "single", "--ticker", ticker]
    if company:
        parts.extend(["--name", _quote(company)])
    if market:
        parts.extend(["--market", _quote(market)])
    return " ".join(parts) + "  # template only; do not execute without approval"


def candidates_to_csv_rows(candidates: list[RefreshCandidate] | tuple[RefreshCandidate, ...]) -> list[dict[str, Any]]:
    return [candidate.to_csv_row() for candidate in candidates]


def _candidate_table(candidates: list[RefreshCandidate] | tuple[RefreshCandidate, ...]) -> str:
    headers = [
        "priority_rank",
        "ticker",
        "company",
        "queue",
        "refresh_score",
        "latest_action",
        "latest_rating",
        "pm_score",
        "chokepoint_score",
        "confidence",
        "latest_run_date",
        "reasons",
    ]
    rows = [
        [
            candidate.priority_rank,
            candidate.ticker,
            candidate.company,
            candidate.queue,
            candidate.refresh_score,
            candidate.latest_action,
            candidate.latest_rating,
            candidate.pm_score,
            candidate.chokepoint_score,
            candidate.confidence,
            candidate.latest_run_date,
            ", ".join(candidate.reason_codes),
        ]
        for candidate in candidates
    ]
    if not rows:
        return "No rows."
    return table(headers, rows)


def _reason_table(reason_counts: dict[str, int]) -> str:
    rows = [
        [code, count, REASON_EXPLANATIONS.get(code, "No explanation registered.")]
        for code, count in reason_counts.items()
    ]
    if not rows:
        return "No reason codes."
    return table(["reason_code", "count", "explanation"], rows)


def _counts_text(counts: dict[str, Any]) -> str:
    if not counts:
        return "N/A"
    return ", ".join(f"{key}: {value}" for key, value in counts.items())


def _quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'

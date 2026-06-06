"""Offline approval packet generator for refresh candidates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_pm_agent.approval.manifest import manifest_rows
from ai_pm_agent.approval.templates import (
    APPROVAL_CHECKLIST,
    COMMAND_BUNDLE_HEADER,
    KNOWN_LIMITATIONS,
    MANIFEST_FIELDS,
    REASON_GROUPS,
    dossier_path_for_ticker,
)
from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.refresh.planner import RefreshCandidate, RefreshPlan, RefreshPlanner
from ai_pm_agent.refresh.queues import (
    HIGH_PRIORITY,
    NO_REFRESH_NEEDED,
    NORMAL_REFRESH,
    QUEUE_ORDER,
    REASON_EXPLANATIONS,
    URGENT_REFRESH,
)
from ai_pm_agent.reports.markdown import bullet_list, cell, display, generated_at, table


DEFAULT_REVIEW_QUEUES = {URGENT_REFRESH, HIGH_PRIORITY, NORMAL_REFRESH}


@dataclass(frozen=True)
class ApprovalPacketOptions:
    queues: tuple[str, ...] = ()
    min_score: float | None = None
    limit: int | None = 25
    tickers: tuple[str, ...] = ()
    include_monitor_only: bool = False
    exclude_no_refresh_needed: bool = True
    refresh_csv: str | None = None


@dataclass(frozen=True)
class ApprovalPacketResult:
    plan: RefreshPlan
    selected_candidates: tuple[RefreshCandidate, ...]
    markdown: str
    manifest_rows: list[dict[str, Any]]
    command_bundle: str


class ApprovalPacketGenerator:
    """Build review-only approval packets from SQLite-backed refresh candidates."""

    def __init__(self, repo: CompanyResearchRepository, planner: RefreshPlanner | None = None):
        self.repo = repo
        self.planner = planner or RefreshPlanner(repo)

    def build(self, options: ApprovalPacketOptions | None = None) -> ApprovalPacketResult:
        options = options or ApprovalPacketOptions()
        plan = self.planner.build_plan()
        selected = tuple(self.select_candidates(plan, options))
        rows = manifest_rows(selected)
        return ApprovalPacketResult(
            plan=plan,
            selected_candidates=selected,
            markdown=self.render_packet(plan, selected, options, rows),
            manifest_rows=rows,
            command_bundle=self.render_command_bundle(selected),
        )

    def select_candidates(
        self, plan: RefreshPlan, options: ApprovalPacketOptions
    ) -> list[RefreshCandidate]:
        candidates = list(plan.candidates)
        requested_tickers = {ticker.strip().upper() for ticker in options.tickers if ticker.strip()}
        requested_queues = {queue for queue in options.queues if queue}

        if requested_tickers:
            candidates = [candidate for candidate in candidates if candidate.ticker.upper() in requested_tickers]

        if requested_queues:
            candidates = [candidate for candidate in candidates if candidate.queue in requested_queues]
        else:
            allowed = set(DEFAULT_REVIEW_QUEUES)
            if options.include_monitor_only:
                allowed.add("monitor_only")
            candidates = [candidate for candidate in candidates if candidate.queue in allowed]

        if options.exclude_no_refresh_needed:
            candidates = [candidate for candidate in candidates if candidate.queue != NO_REFRESH_NEEDED]

        if options.min_score is not None:
            candidates = [
                candidate for candidate in candidates if float(candidate.refresh_score or 0) >= options.min_score
            ]

        candidates.sort(
            key=lambda candidate: (
                QUEUE_ORDER.index(candidate.queue),
                -int(candidate.refresh_score or 0),
                candidate.priority_rank,
                candidate.ticker,
            )
        )
        if options.limit is not None and options.limit >= 0:
            candidates = candidates[: options.limit]
        return candidates

    def render_packet(
        self,
        plan: RefreshPlan,
        candidates: tuple[RefreshCandidate, ...],
        options: ApprovalPacketOptions,
        rows: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# Research Refresh Approval Packet",
            "",
            "## 1. Executive Summary",
            "",
            self._executive_summary(plan, candidates, options),
            "",
            "## 2. Proposed Refresh Queue",
            "",
            self._proposed_queue_table(candidates),
            "",
            "## 3. Why These Companies Were Selected",
            "",
            self._reason_group_tables(candidates),
            "",
            "## 4. Company Review Cards",
            "",
            self._company_review_cards(candidates),
            "",
            "## 5. Suggested Manual Commands",
            "",
            self._suggested_commands(candidates),
            "",
            "## 6. Approval Checklist",
            "",
            bullet_list(APPROVAL_CHECKLIST),
            "",
            "## 7. Approval Manifest Preview",
            "",
            self._manifest_preview(rows),
            "",
            "## 8. Known Limitations",
            "",
            bullet_list(KNOWN_LIMITATIONS),
            "",
        ]
        return "\n".join(lines).strip() + "\n"

    def render_command_bundle(self, candidates: tuple[RefreshCandidate, ...]) -> str:
        lines = [
            COMMAND_BUNDLE_HEADER,
            "",
            "All commands below are template only; human approval is required.",
            "",
        ]
        if not candidates:
            lines.append("No command templates generated because no candidates matched the packet filters.")
        else:
            for candidate in candidates:
                lines.append(f"# {candidate.priority_rank}. {candidate.ticker} - {candidate.company}")
                lines.append(candidate.suggested_manual_command)
                lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _executive_summary(
        self,
        plan: RefreshPlan,
        candidates: tuple[RefreshCandidate, ...],
        options: ApprovalPacketOptions,
    ) -> str:
        selected_counts = Counter(candidate.queue for candidate in candidates)
        items = [
            f"Generated: {generated_at()}",
            f"DB path: `{plan.db_path}`",
            f"Companies evaluated: {plan.companies_evaluated}",
            f"Candidates included: {len(candidates)}",
            "All queue breakdown: " + _counts_text(plan.queue_counts),
            "Selected queue breakdown: " + _counts_text({queue: selected_counts.get(queue, 0) for queue in QUEUE_ORDER}),
            "Top 10 candidates: " + _top_candidate_text(candidates[:10]),
            "Highest-risk data quality issues: " + _quality_issue_text(candidates),
            "This packet does not execute reruns.",
        ]
        if options.refresh_csv:
            items.append(f"Refresh CSV reference: `{options.refresh_csv}`. This file was not parsed as input.")
        return bullet_list(items)

    def _proposed_queue_table(self, candidates: tuple[RefreshCandidate, ...]) -> str:
        if not candidates:
            return "No candidates matched the approval packet filters."
        headers = [
            "rank",
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
        ]
        rows = [
            [
                candidate.priority_rank,
                candidate.ticker,
                candidate.company,
                candidate.market,
                candidate.queue,
                candidate.refresh_score,
                candidate.latest_action,
                candidate.latest_rating,
                candidate.pm_score,
                candidate.chokepoint_score,
                candidate.confidence,
                candidate.latest_run_date,
                candidate.warning_count,
                candidate.evidence_count,
                candidate.fact_count,
                ", ".join(candidate.reason_codes),
            ]
            for candidate in candidates
        ]
        return table(headers, rows)

    def _reason_group_tables(self, candidates: tuple[RefreshCandidate, ...]) -> str:
        if not candidates:
            return "No reason-code groups because no candidates matched the filters."

        blocks: list[str] = []
        for group_name, codes in REASON_GROUPS:
            rows = []
            for code in sorted(codes):
                tickers = [candidate.ticker for candidate in candidates if code in candidate.reason_codes]
                if tickers:
                    rows.append([code, REASON_EXPLANATIONS.get(code, "No explanation registered."), ", ".join(tickers)])
            if rows:
                blocks.extend([f"### {group_name}", "", table(["reason_code", "explanation", "tickers"], rows), ""])
        return "\n".join(blocks).strip() if blocks else "No grouped reason codes found for selected candidates."

    def _company_review_cards(self, candidates: tuple[RefreshCandidate, ...]) -> str:
        if not candidates:
            return "No company review cards because no candidates matched the filters."

        cards: list[str] = []
        for candidate in candidates:
            dossier_path = dossier_path_for_ticker(candidate.ticker)
            cards.extend(
                [
                    f"### {candidate.priority_rank}. {candidate.ticker} - {candidate.company}",
                    "",
                    _dossier_excerpt(candidate),
                    "",
                    table(
                        ["Field", "Value"],
                        [
                            ("queue", candidate.queue),
                            ("refresh_score", candidate.refresh_score),
                            ("latest action/rating", f"{display(candidate.latest_action)} / {display(candidate.latest_rating)}"),
                            ("PM score", candidate.pm_score),
                            ("chokepoint score", candidate.chokepoint_score),
                            ("confidence", candidate.confidence),
                            ("latest run date", candidate.latest_run_date),
                            ("evidence count", candidate.evidence_count),
                            ("fact count", candidate.fact_count),
                            ("warning count", candidate.warning_count),
                            ("reason codes", ", ".join(candidate.reason_codes)),
                            ("latest artifact path", candidate.artifact_path),
                            ("existing dossier path", dossier_path),
                            ("suggested manual command", candidate.suggested_manual_command),
                        ],
                    ),
                    "",
                    "Checklist:",
                    "",
                    bullet_list(_review_checklist(candidate)),
                    "",
                ]
            )
        return "\n".join(cards).strip()

    def _suggested_commands(self, candidates: tuple[RefreshCandidate, ...]) -> str:
        if not candidates:
            return "No suggested manual commands because no candidates matched the filters."
        lines = [
            "Template only; human approval required. Confirm arguments before running live research.",
            "",
            "```powershell",
        ]
        lines.extend(candidate.suggested_manual_command for candidate in candidates)
        lines.append("```")
        return "\n".join(lines)

    def _manifest_preview(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return table(MANIFEST_FIELDS, [])
        preview = rows[:10]
        return table(MANIFEST_FIELDS, [[row.get(field) for field in MANIFEST_FIELDS] for row in preview])


def explain_packet_text(manifest_summary: dict[str, Any], db_path: str) -> str:
    if not manifest_summary.get("exists"):
        return f"Manifest: {manifest_summary.get('path')}\nStatus: missing\nDB path: {db_path}\n"
    lines = [
        f"Manifest: {manifest_summary.get('path')}",
        f"DB path: {db_path}",
        f"Rows: {manifest_summary.get('row_count', 0)}",
        f"Approved rows: {manifest_summary.get('approved_count', 0)}",
        "Queue counts: " + _counts_text(manifest_summary.get("queue_counts", {})),
        "Top tickers: " + (", ".join(manifest_summary.get("top_tickers", [])) or "N/A"),
        "Expected review columns: approved, ticker, queue, refresh_score, reason_codes, suggested_manual_command, notes",
        "This command explains the manifest only; it does not execute reruns.",
    ]
    return "\n".join(lines) + "\n"


def _top_candidate_text(candidates: tuple[RefreshCandidate, ...]) -> str:
    if not candidates:
        return "N/A"
    return ", ".join(f"{candidate.ticker} ({candidate.queue}, {candidate.refresh_score})" for candidate in candidates)


def _quality_issue_text(candidates: tuple[RefreshCandidate, ...]) -> str:
    issues = []
    for candidate in candidates:
        flags = []
        if candidate.warning_count >= 5:
            flags.append(f"warnings={candidate.warning_count}")
        if candidate.evidence_count == 0:
            flags.append("no_evidence")
        if candidate.fact_count == 0:
            flags.append("no_facts")
        if "high_chokepoint_low_confidence" in candidate.reason_codes:
            flags.append("high_chokepoint_low_confidence")
        if flags:
            issues.append(f"{candidate.ticker}: {', '.join(flags)}")
    return "; ".join(issues[:10]) if issues else "N/A"


def _dossier_excerpt(candidate: RefreshCandidate) -> str:
    return (
        "Dossier excerpt (DB-derived): "
        f"{candidate.ticker} is in `{candidate.queue}` with refresh score "
        f"{display(candidate.refresh_score)}. Latest action/rating is "
        f"{display(candidate.latest_action)} / {display(candidate.latest_rating)}; "
        f"PM score {display(candidate.pm_score)}, chokepoint score {display(candidate.chokepoint_score)}, "
        f"confidence {display(candidate.confidence)}. Indexed evidence/facts/warnings: "
        f"{candidate.evidence_count}/{candidate.fact_count}/{candidate.warning_count}."
    )


def _review_checklist(candidate: RefreshCandidate) -> list[str]:
    reasons = set(candidate.reason_codes)
    return [
        "rerun because stale? " + _yes_no(bool(reasons & {"stale_gt_30d", "stale_gt_14d", "stale_gt_7d"})),
        "rerun because evidence/facts missing? " + _yes_no(candidate.evidence_count == 0 or candidate.fact_count == 0),
        "rerun because high chokepoint but low confidence? "
        + _yes_no("high_chokepoint_low_confidence" in reasons),
        "rerun because score/action changed? "
        + _yes_no(bool(reasons & {"action_changed", "rating_changed", "pm_score_changed", "chokepoint_score_changed"})),
        "rerun because data quality warnings are high? " + _yes_no("high_warning_count" in reasons),
    ]


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _counts_text(counts: dict[str, Any]) -> str:
    if not counts:
        return "N/A"
    return ", ".join(f"{cell(key)}: {cell(value)}" for key, value in counts.items())

"""Offline manual runbook generation for approved research refresh commands.

This module creates review documents only. It does not execute commands and
does not spawn subprocesses.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.refresh.queues import QUEUE_ORDER
from ai_pm_agent.reports.markdown import bullet_list, cell, generated_at, table, write_csv, write_text


RUNBOOK_CSV_FIELDS = [
    "batch",
    "step",
    "rank",
    "ticker",
    "company",
    "market",
    "queue",
    "refresh_score",
    "reason_codes",
    "command",
    "expected_output_template",
    "pre_run_checked",
    "post_run_status",
    "notes",
]

PRE_RUN_CHECKLIST = [
    "Confirm approved rows were manually reviewed.",
    "Confirm tickers and markets are correct.",
    "Confirm ai_pm_agent.py command syntax is correct.",
    "Confirm live LLM/web/yfinance usage is allowed.",
    "Confirm .env and API keys are configured locally but not exposed.",
    "Confirm output folders should be newly created, not overwritten.",
    "Confirm expected cost/time budget.",
    "Confirm no broker/trading/execution code will run.",
    "Confirm commands are copied manually, not auto-executed by this tool.",
]

POST_RUN_CHECKLIST = [
    "Confirm each command completed successfully.",
    "Confirm new outputs folder was created.",
    "Confirm pm_decision.json exists for each rerun.",
    "Confirm quality_report.md exists where expected.",
    "Rerun company DB import.",
    "Rerun stats/latest/rank commands.",
    "Regenerate company dossier.",
    "Regenerate refresh planner.",
    "Regenerate approval packet if needed.",
]

POST_RUN_COMMANDS = [
    "python scripts\\company_db_import.py import --outputs outputs --db data\\company_db\\company_research.sqlite",
    "python scripts\\company_db_import.py stats --db data\\company_db\\company_research.sqlite",
    (
        "python scripts\\company_db_report.py top-chokepoints --db "
        "data\\company_db\\company_research.sqlite --limit 25 --out reports\\watchlists\\top_chokepoints.md"
    ),
    (
        "python scripts\\company_db_refresh.py plan --db data\\company_db\\company_research.sqlite "
        "--out reports\\refresh\\refresh_plan.md --csv reports\\refresh\\refresh_queue.csv"
    ),
]

LIMITATIONS = [
    "Offline runbook only.",
    "No command execution is performed.",
    "No live data verification is performed.",
    "Command syntax is template-based.",
    "Human must manually copy/paste commands.",
    "This tool does not guarantee API availability or research quality.",
]


@dataclass(frozen=True)
class RunbookRow:
    row: dict[str, str]

    @property
    def status(self) -> str:
        return self.row.get("validation_status", "").strip()

    @property
    def is_valid_approved(self) -> bool:
        return self.status == "valid_approved"

    @property
    def ticker(self) -> str:
        return self.row.get("ticker", "").strip()

    @property
    def queue(self) -> str:
        return self.row.get("queue", "").strip()

    @property
    def refresh_score(self) -> float | None:
        try:
            value = self.row.get("refresh_score", "").strip()
            return float(value) if value else None
        except ValueError:
            return None


@dataclass(frozen=True)
class RunbookBatch:
    number: int
    rows: tuple[RunbookRow, ...]


@dataclass(frozen=True)
class ApprovedCommandsInput:
    path: str
    exists: bool
    line_count: int
    warning: str = ""


@dataclass(frozen=True)
class ManualRunbookResult:
    db_path: str
    validated_manifest_path: str
    approved_commands_path: str
    generated_at: str
    rows: tuple[RunbookRow, ...]
    batches: tuple[RunbookBatch, ...]
    markdown: str
    csv_rows: list[dict[str, Any]]
    commands_input: ApprovedCommandsInput
    db_summary: dict[str, Any]

    @property
    def status_counts(self) -> dict[str, int]:
        counts = Counter(row.status or "unknown" for row in self.rows)
        return {status: counts.get(status, 0) for status in _status_order()}

    @property
    def valid_approved_rows(self) -> tuple[RunbookRow, ...]:
        return tuple(row for row in self.rows if row.is_valid_approved)


class ManualRunbookGenerator:
    """Build offline manual execution runbooks from validated approval artifacts."""

    def __init__(self, repo: CompanyResearchRepository):
        self.repo = repo

    def build(
        self,
        validated_manifest_path: Path | str,
        approved_commands_path: Path | str,
        batch_size: int = 5,
    ) -> ManualRunbookResult:
        batch_size = max(1, int(batch_size or 5))
        rows = tuple(RunbookRow(row) for row in read_validated_manifest(validated_manifest_path))
        commands_input = read_approved_commands_input(approved_commands_path)
        db_summary = self.repo.summarize_database()
        valid_rows = tuple(row for row in rows if row.is_valid_approved)
        batches = tuple(
            RunbookBatch(index, tuple(valid_rows[start : start + batch_size]))
            for index, start in enumerate(range(0, len(valid_rows), batch_size), start=1)
        )
        csv_rows = self.to_csv_rows(batches)
        generated = generated_at()
        result = ManualRunbookResult(
            db_path=str(self.repo.db_path),
            validated_manifest_path=str(validated_manifest_path),
            approved_commands_path=str(approved_commands_path),
            generated_at=generated,
            rows=rows,
            batches=batches,
            markdown="",
            csv_rows=csv_rows,
            commands_input=commands_input,
            db_summary=db_summary,
        )
        markdown = self.render_markdown(result)
        return ManualRunbookResult(
            db_path=result.db_path,
            validated_manifest_path=result.validated_manifest_path,
            approved_commands_path=result.approved_commands_path,
            generated_at=result.generated_at,
            rows=result.rows,
            batches=result.batches,
            markdown=markdown,
            csv_rows=result.csv_rows,
            commands_input=result.commands_input,
            db_summary=result.db_summary,
        )

    def write(
        self,
        validated_manifest_path: Path | str,
        approved_commands_path: Path | str,
        markdown_out: Path | str,
        csv_out: Path | str,
        batch_size: int = 5,
    ) -> ManualRunbookResult:
        result = self.build(validated_manifest_path, approved_commands_path, batch_size=batch_size)
        write_text(markdown_out, result.markdown)
        write_csv(csv_out, result.csv_rows, RUNBOOK_CSV_FIELDS)
        return result

    def to_csv_rows(self, batches: tuple[RunbookBatch, ...]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        step = 1
        for batch in batches:
            for row in batch.rows:
                source = row.row
                output.append(
                    {
                        "batch": batch.number,
                        "step": step,
                        "rank": source.get("rank", ""),
                        "ticker": source.get("ticker", ""),
                        "company": source.get("company", ""),
                        "market": source.get("market", ""),
                        "queue": source.get("queue", ""),
                        "refresh_score": source.get("refresh_score", ""),
                        "reason_codes": source.get("reason_codes", ""),
                        "command": source.get("suggested_manual_command", ""),
                        "expected_output_template": expected_output_template(source.get("ticker", "")),
                        "pre_run_checked": "",
                        "post_run_status": "",
                        "notes": "",
                    }
                )
                step += 1
        return output

    def render_markdown(self, result: ManualRunbookResult) -> str:
        valid_count = len(result.valid_approved_rows)
        lines = [
            "# Manual Research Refresh Runbook",
            "",
            "## 1. Executive Summary",
            "",
            self._executive_summary(result),
            "",
            "## 2. Current Approval Status",
            "",
            _status_table(result.rows),
            "",
        ]
        if valid_count == 0:
            lines.extend(
                [
                    "No commands are approved for execution. Edit approval_manifest.csv, rerun validation, and regenerate this runbook.",
                    "",
                ]
            )
        lines.extend(
            [
                "## 3. Pre-Run Safety Checklist",
                "",
                bullet_list(PRE_RUN_CHECKLIST),
                "",
                "## 4. Execution Batches",
                "",
                self._execution_batches(result.batches),
                "",
                "## 5. Post-Run Verification Checklist",
                "",
                bullet_list(POST_RUN_CHECKLIST),
                "",
                "Suggested post-run offline commands. Do not run automatically:",
                "",
                "```powershell",
                *POST_RUN_COMMANDS,
                "```",
                "",
                "## 6. Excluded Rows",
                "",
                _excluded_rows_table(result.rows),
                "",
                "## 7. Limitations",
                "",
                bullet_list(LIMITATIONS),
                "",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _executive_summary(self, result: ManualRunbookResult) -> str:
        items = [
            f"Generated: {result.generated_at}",
            f"DB path: `{result.db_path}`",
            f"Validated manifest path: `{result.validated_manifest_path}`",
            f"Approved commands path: `{result.approved_commands_path}`",
            f"DB companies indexed: {result.db_summary.get('counts', {}).get('companies', 'N/A')}",
            f"Total manifest rows: {len(result.rows)}",
            f"Valid approved rows: {len(result.valid_approved_rows)}",
            f"Invalid approved rows: {_count_status(result.rows, 'invalid_approved')}",
            f"Ambiguous approval rows: {_count_status(result.rows, 'ambiguous_approval')}",
            f"Commands included: {len(result.valid_approved_rows)}",
            f"Batch count: {len(result.batches)}",
            "This runbook does not execute commands.",
        ]
        if result.commands_input.warning:
            items.append(result.commands_input.warning)
        else:
            items.append(f"Approved commands file lines read: {result.commands_input.line_count}")
        return bullet_list(items)

    def _execution_batches(self, batches: tuple[RunbookBatch, ...]) -> str:
        if not batches:
            return "No execution batches because there are no valid approved commands."
        blocks: list[str] = []
        for batch in batches:
            rows = batch.rows
            blocks.extend(
                [
                    f"### Batch {batch.number}",
                    "",
                    bullet_list(
                        [
                            "Tickers: " + ", ".join(row.ticker for row in rows),
                            "Queue mix: " + _counts_text(Counter(row.queue for row in rows)),
                            "Max refresh score: " + _max_score_text(rows),
                            "Reason-code summary: " + _reason_summary(rows),
                            "Estimated output location template: `outputs\\{YYYYMMDD}\\{ticker}_YYYYMMDD_HHMMSS`",
                        ]
                    ),
                    "",
                    "```powershell",
                ]
            )
            for row in rows:
                source = row.row
                blocks.append(
                    "# "
                    f"rank={cell(source.get('rank', ''))} "
                    f"ticker={cell(source.get('ticker', ''))} "
                    f"company={cell(source.get('company', ''))} "
                    f"queue={cell(source.get('queue', ''))} "
                    f"score={cell(source.get('refresh_score', ''))}"
                )
                blocks.append(source.get("suggested_manual_command", ""))
                blocks.append("")
            blocks.extend(["```", ""])
        return "\n".join(blocks).strip()


def read_validated_manifest(path: Path | str) -> list[dict[str, str]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Validated manifest does not exist: {target}")
    if target.stat().st_size == 0:
        return []
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: value or "" for key, value in row.items() if key is not None} for row in reader]


def read_approved_commands_input(path: Path | str) -> ApprovedCommandsInput:
    target = Path(path)
    if not target.exists():
        return ApprovedCommandsInput(
            path=str(target),
            exists=False,
            line_count=0,
            warning=f"Approved commands file not found: `{target}`. Runbook generated from validated manifest only.",
        )
    text = target.read_text(encoding="utf-8")
    return ApprovedCommandsInput(path=str(target), exists=True, line_count=len(text.splitlines()))


def expected_output_template(ticker: str) -> str:
    safe = (ticker or "{ticker}").replace(".", "_").replace("/", "_").replace("\\", "_")
    return f"outputs\\{{YYYYMMDD}}\\{safe}_YYYYMMDD_HHMMSS"


def _status_order() -> list[str]:
    return ["valid_approved", "invalid_approved", "ambiguous_approval", "not_approved"]


def _status_table(rows: tuple[RunbookRow, ...]) -> str:
    counts = Counter(row.status or "unknown" for row in rows)
    return table(["status", "count"], [[status, counts.get(status, 0)] for status in _status_order()])


def _excluded_rows_table(rows: tuple[RunbookRow, ...]) -> str:
    excluded = [row for row in rows if row.status in {"invalid_approved", "ambiguous_approval"}]
    if not excluded:
        return "No invalid or ambiguous rows."
    return table(
        ["rank", "ticker", "company", "validation_status", "validation_errors", "validation_warnings"],
        [
            [
                row.row.get("rank", ""),
                row.row.get("ticker", ""),
                row.row.get("company", ""),
                row.row.get("validation_status", ""),
                row.row.get("validation_errors", ""),
                row.row.get("validation_warnings", ""),
            ]
            for row in excluded
        ],
    )


def _count_status(rows: tuple[RunbookRow, ...], status: str) -> int:
    return sum(1 for row in rows if row.status == status)


def _counts_text(counts: Counter[str]) -> str:
    if not counts:
        return "N/A"
    ordered = [queue for queue in QUEUE_ORDER if counts.get(queue)]
    ordered.extend(sorted(queue for queue in counts if queue not in QUEUE_ORDER))
    return ", ".join(f"{queue}: {counts[queue]}" for queue in ordered)


def _max_score_text(rows: tuple[RunbookRow, ...]) -> str:
    scores = [row.refresh_score for row in rows if row.refresh_score is not None]
    if not scores:
        return "N/A"
    value = max(scores)
    return str(int(value)) if value.is_integer() else str(value)


def _reason_summary(rows: tuple[RunbookRow, ...]) -> str:
    counts: Counter[str] = Counter()
    for row in rows:
        for reason in row.row.get("reason_codes", "").split(","):
            reason = reason.strip()
            if reason:
                counts[reason] += 1
    if not counts:
        return "N/A"
    return ", ".join(f"{reason}: {count}" for reason, count in counts.most_common())

"""Approved command extraction helpers.

The functions in this module only write command templates. They never execute
commands or spawn subprocesses.
"""

from __future__ import annotations

from pathlib import Path

from ai_pm_agent.approval.validator import (
    VALIDATED_MANIFEST_FIELDS,
    ApprovalValidationResult,
    ValidatedApprovalRow,
    render_validation_report,
)
from ai_pm_agent.refresh.queues import QUEUE_ORDER
from ai_pm_agent.reports.markdown import cell, write_csv, write_text


APPROVED_COMMANDS_HEADER = """DO NOT RUN AUTOMATICALLY.
These commands were extracted from manually approved manifest rows.
Review each command before execution.
This file was generated offline and did not execute anything."""


def render_approved_commands(result: ApprovalValidationResult) -> str:
    lines = [APPROVED_COMMANDS_HEADER, ""]
    rows = result.valid_approved_rows
    if not rows:
        lines.append("No valid approved commands were found.")
        return "\n".join(lines).strip() + "\n"

    for queue in QUEUE_ORDER:
        queue_rows = [row for row in rows if row.source_row.get("queue") == queue]
        if not queue_rows:
            continue
        lines.append(f"## {queue}")
        lines.append("")
        for row in queue_rows:
            lines.append(command_comment(row))
            lines.append(row.source_row.get("suggested_manual_command", ""))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_approved_command_outputs(
    result: ApprovalValidationResult,
    commands_out: Path | str,
    manifest_out: Path | str,
    validation_out: Path | str,
    include_not_approved: bool = False,
) -> None:
    write_text(commands_out, render_approved_commands(result))
    write_csv(manifest_out, result.to_csv_rows(), VALIDATED_MANIFEST_FIELDS)
    write_text(validation_out, render_validation_report(result, include_not_approved=include_not_approved))


def command_comment(row: ValidatedApprovalRow) -> str:
    source = row.source_row
    return (
        "# "
        f"rank={cell(source.get('rank', ''))} "
        f"ticker={cell(source.get('ticker', ''))} "
        f"company={cell(source.get('company', ''))} "
        f"score={cell(source.get('refresh_score', ''))} "
        f"reasons={cell(source.get('reason_codes', ''))}"
    )

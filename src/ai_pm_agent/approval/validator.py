"""Validation for manually edited approval manifests.

This module is intentionally review-only. It never executes suggested commands.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ai_pm_agent.approval.templates import MANIFEST_FIELDS
from ai_pm_agent.company_db.repository import CompanyResearchRepository
from ai_pm_agent.refresh.queues import QUEUE_ORDER
from ai_pm_agent.reports.markdown import bullet_list, cell, generated_at, table, write_csv, write_text


APPROVED_VALUES = {"true", "yes", "y", "1", "approve", "approved", "x"}
NOT_APPROVED_VALUES = {"", "false", "no", "n", "0"}
REQUIRED_APPROVED_FIELDS = [
    "ticker",
    "company",
    "queue",
    "refresh_score",
    "reason_codes",
    "suggested_manual_command",
]
VALIDATED_MANIFEST_FIELDS = [
    "approved",
    "validation_status",
    "validation_errors",
    "validation_warnings",
    *[field for field in MANIFEST_FIELDS if field != "approved"],
]

DANGEROUS_WORD_PATTERNS = [
    r"\bpowershell\b",
    r"\bcmd\s*/c\b",
    r"\bdel\b",
    r"\berase\b",
    r"\brm\b",
    r"\brmdir\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\binvoke-webrequest\b",
    r"\biwr\b",
    r"\bstart-process\b",
]


@dataclass(frozen=True)
class ApprovalParseResult:
    approved: bool
    ambiguous: bool
    normalized_value: str
    warning: str = ""


@dataclass(frozen=True)
class ValidatedApprovalRow:
    source_row: dict[str, str]
    row_number: int
    approved: bool
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def is_valid_approved(self) -> bool:
        return self.status == "valid_approved"

    def to_csv_row(self) -> dict[str, Any]:
        row = {field: self.source_row.get(field, "") for field in MANIFEST_FIELDS}
        return {
            "approved": row.get("approved", ""),
            "validation_status": self.status,
            "validation_errors": "; ".join(self.errors),
            "validation_warnings": "; ".join(self.warnings),
            **{field: row.get(field, "") for field in MANIFEST_FIELDS if field != "approved"},
        }


@dataclass(frozen=True)
class ApprovalValidationResult:
    db_path: str
    manifest_path: str
    generated_at: str
    rows: tuple[ValidatedApprovalRow, ...]

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def approved_rows(self) -> int:
        return sum(1 for row in self.rows if row.approved)

    @property
    def valid_approved_rows(self) -> tuple[ValidatedApprovalRow, ...]:
        return tuple(row for row in self.rows if row.status == "valid_approved")

    @property
    def invalid_approved_rows(self) -> tuple[ValidatedApprovalRow, ...]:
        return tuple(row for row in self.rows if row.status == "invalid_approved")

    @property
    def ambiguous_rows(self) -> tuple[ValidatedApprovalRow, ...]:
        return tuple(row for row in self.rows if row.status == "ambiguous_approval")

    @property
    def not_approved_rows(self) -> tuple[ValidatedApprovalRow, ...]:
        return tuple(row for row in self.rows if row.status == "not_approved")

    def to_csv_rows(self) -> list[dict[str, Any]]:
        return [row.to_csv_row() for row in self.rows]


class ApprovalManifestValidator:
    """Validate human-approved manifest rows against the company database."""

    def __init__(self, repo: CompanyResearchRepository):
        self.repo = repo

    def validate(self, manifest_path: Path | str) -> ApprovalValidationResult:
        rows = read_manifest_rows(manifest_path)
        validated = [self.validate_row(row, index) for index, row in enumerate(rows, start=2)]
        return ApprovalValidationResult(
            db_path=str(self.repo.db_path),
            manifest_path=str(manifest_path),
            generated_at=generated_at(),
            rows=tuple(validated),
        )

    def validate_row(self, row: dict[str, str], row_number: int) -> ValidatedApprovalRow:
        approval = parse_approved_value(row.get("approved", ""))
        warnings: list[str] = []
        errors: list[str] = []
        if approval.warning:
            warnings.append(approval.warning)

        if approval.ambiguous:
            return ValidatedApprovalRow(
                source_row=row,
                row_number=row_number,
                approved=False,
                status="ambiguous_approval",
                errors=tuple(errors),
                warnings=tuple(warnings),
            )

        if not approval.approved:
            return ValidatedApprovalRow(
                source_row=row,
                row_number=row_number,
                approved=False,
                status="not_approved",
                errors=tuple(errors),
                warnings=tuple(warnings),
            )

        errors.extend(_missing_required_fields(row))
        ticker = _text(row.get("ticker")).upper()
        company = _text(row.get("company"))
        if ticker:
            db_company = self.repo.get_company_by_ticker(ticker)
            if db_company is None:
                errors.append("ticker_not_found_in_db")
            else:
                db_name = _text(db_company["company"])
                if company and not company_names_roughly_match(company, db_name):
                    warnings.append(f"company_mismatch_db={db_name}")

        queue = _text(row.get("queue"))
        if queue and queue not in QUEUE_ORDER:
            errors.append("invalid_queue")

        score = _parse_score(row.get("refresh_score"))
        if score is None:
            errors.append("refresh_score_not_numeric")
        elif score < 0 or score > 100:
            errors.append("refresh_score_outside_0_100")

        command = _text(row.get("suggested_manual_command"))
        if command:
            dangerous = dangerous_command_patterns(command)
            if dangerous:
                errors.append("dangerous_command_pattern=" + ",".join(dangerous))

        status = "invalid_approved" if errors else "valid_approved"
        return ValidatedApprovalRow(
            source_row=row,
            row_number=row_number,
            approved=True,
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )


def parse_approved_value(value: Any) -> ApprovalParseResult:
    normalized = _text(value).lower()
    if normalized in APPROVED_VALUES:
        return ApprovalParseResult(approved=True, ambiguous=False, normalized_value=normalized)
    if normalized in NOT_APPROVED_VALUES:
        return ApprovalParseResult(approved=False, ambiguous=False, normalized_value=normalized)
    return ApprovalParseResult(
        approved=False,
        ambiguous=True,
        normalized_value=normalized,
        warning=f"ambiguous_approved_value={_text(value)}",
    )


def read_manifest_rows(path: Path | str) -> list[dict[str, str]]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Approval manifest does not exist: {target}")
    if target.stat().st_size == 0:
        return []
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: value or "" for key, value in row.items() if key is not None} for row in reader]


def render_validation_report(result: ApprovalValidationResult, include_not_approved: bool = False) -> str:
    lines = [
        "# Approval Manifest Validation Report",
        "",
        "## 1. Summary",
        "",
        bullet_list(
            [
                f"Generated: {result.generated_at}",
                f"DB path: `{result.db_path}`",
                f"Manifest path: `{result.manifest_path}`",
                f"Total rows: {result.total_rows}",
                f"Approved rows: {result.approved_rows}",
                f"Valid approved rows: {len(result.valid_approved_rows)}",
                f"Invalid approved rows: {len(result.invalid_approved_rows)}",
                f"Ambiguous approval rows: {len(result.ambiguous_rows)}",
                f"Not approved rows: {len(result.not_approved_rows)}",
            ]
        ),
        "",
        "## 2. Valid Approved Commands",
        "",
        _valid_approved_table(result.valid_approved_rows),
        "",
        "## 3. Invalid Approved Rows",
        "",
        _invalid_rows_table(result.invalid_approved_rows),
        "",
        "## 4. Ambiguous Approval Rows",
        "",
        _ambiguous_rows_table(result.ambiguous_rows),
        "",
        "## 5. Not Approved Rows",
        "",
    ]
    if include_not_approved:
        lines.append(_not_approved_table(result.not_approved_rows))
    else:
        lines.append(f"Count: {len(result.not_approved_rows)}")
    lines.extend(
        [
            "",
            "## 6. Safety Notes",
            "",
            bullet_list(
                [
                    "No commands were executed.",
                    "This validator only extracts templates.",
                    "Human must review commands before running.",
                    "Live rerun phase requires separate approval.",
                ]
            ),
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_dry_run_report(result: ApprovalValidationResult) -> str:
    lines = [
        "# Approved Commands Dry Run",
        "",
        "## Summary",
        "",
        bullet_list(
            [
                f"Valid approved commands count: {len(result.valid_approved_rows)}",
                f"Invalid approved rows count: {len(result.invalid_approved_rows)}",
                f"Ambiguous approval rows count: {len(result.ambiguous_rows)}",
                "No commands executed.",
            ]
        ),
        "",
        "## Commands That Would Be Included",
        "",
        _commands_by_queue(result.valid_approved_rows),
        "",
        "## Rows Excluded",
        "",
        _excluded_rows_table(tuple(result.invalid_approved_rows) + tuple(result.ambiguous_rows)),
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def write_validation_outputs(
    result: ApprovalValidationResult,
    markdown_path: Path | str,
    csv_path: Path | str | None = None,
    include_not_approved: bool = False,
) -> None:
    write_text(markdown_path, render_validation_report(result, include_not_approved=include_not_approved))
    if csv_path:
        write_csv(csv_path, result.to_csv_rows(), VALIDATED_MANIFEST_FIELDS)


def company_names_roughly_match(manifest_name: str, db_name: str) -> bool:
    left = _normalize_name(manifest_name)
    right = _normalize_name(db_name)
    if not left or not right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.65


def dangerous_command_patterns(command: str) -> list[str]:
    unquoted = _strip_quoted_text(_strip_unquoted_comment(command))
    lowered = unquoted.lower()
    found: list[str] = []
    for pattern in ["&&", "||", "$(", "`", "|", ";", "<", "&"]:
        if pattern in unquoted:
            found.append(pattern)
    for pattern in DANGEROUS_WORD_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            found.append(pattern.replace("\\b", "").replace("\\s*", " ").replace("\\s", " "))
    return found


def _valid_approved_table(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No valid approved commands."
    return table(
        ["rank", "ticker", "company", "queue", "refresh_score", "reasons", "command"],
        [
            [
                row.source_row.get("rank", ""),
                row.source_row.get("ticker", ""),
                row.source_row.get("company", ""),
                row.source_row.get("queue", ""),
                row.source_row.get("refresh_score", ""),
                row.source_row.get("reason_codes", ""),
                row.source_row.get("suggested_manual_command", ""),
            ]
            for row in rows
        ],
    )


def _invalid_rows_table(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No invalid approved rows."
    return table(
        ["rank", "ticker", "company", "validation_errors"],
        [
            [
                row.source_row.get("rank", ""),
                row.source_row.get("ticker", ""),
                row.source_row.get("company", ""),
                "; ".join(row.errors),
            ]
            for row in rows
        ],
    )


def _ambiguous_rows_table(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No ambiguous approval rows."
    return table(
        ["rank", "ticker", "approved_value", "validation_warnings"],
        [
            [
                row.source_row.get("rank", ""),
                row.source_row.get("ticker", ""),
                row.source_row.get("approved", ""),
                "; ".join(row.warnings),
            ]
            for row in rows
        ],
    )


def _not_approved_table(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No not-approved rows."
    return table(
        ["rank", "ticker", "company", "queue"],
        [
            [
                row.source_row.get("rank", ""),
                row.source_row.get("ticker", ""),
                row.source_row.get("company", ""),
                row.source_row.get("queue", ""),
            ]
            for row in rows
        ],
    )


def _commands_by_queue(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No valid approved commands would be included."
    sections: list[str] = []
    for queue in QUEUE_ORDER:
        queue_rows = [row for row in rows if row.source_row.get("queue") == queue]
        if not queue_rows:
            continue
        sections.extend([f"### {queue}", ""])
        for row in queue_rows:
            sections.append(_command_comment(row))
            sections.append(row.source_row.get("suggested_manual_command", ""))
            sections.append("")
    return "\n".join(sections).strip()


def _excluded_rows_table(rows: tuple[ValidatedApprovalRow, ...]) -> str:
    if not rows:
        return "No invalid or ambiguous approved rows were excluded."
    return table(
        ["rank", "ticker", "status", "reason"],
        [
            [
                row.source_row.get("rank", ""),
                row.source_row.get("ticker", ""),
                row.status,
                "; ".join(row.errors or row.warnings),
            ]
            for row in rows
        ],
    )


def _command_comment(row: ValidatedApprovalRow) -> str:
    source = row.source_row
    return (
        "# "
        f"rank={cell(source.get('rank', ''))} "
        f"ticker={cell(source.get('ticker', ''))} "
        f"company={cell(source.get('company', ''))} "
        f"score={cell(source.get('refresh_score', ''))} "
        f"reasons={cell(source.get('reason_codes', ''))}"
    )


def _missing_required_fields(row: dict[str, str]) -> list[str]:
    return [f"missing_{field}" for field in REQUIRED_APPROVED_FIELDS if not _text(row.get(field))]


def _parse_score(value: Any) -> float | None:
    try:
        return float(_text(value))
    except ValueError:
        return None


def _strip_quoted_text(value: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            if quote is None:
                result.append(" ")
            continue
        if char == "\\":
            escaped = True
            if quote is None:
                result.append(char)
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
                result.append(" ")
                continue
            if quote == char:
                quote = None
                result.append(" ")
                continue
        if quote is None:
            result.append(char)
        else:
            result.append(" ")
    return "".join(result)


def _strip_unquoted_comment(value: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            result.append(char)
            continue
        if char == "\\":
            escaped = True
            result.append(char)
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            result.append(char)
            continue
        if char == "#" and quote is None:
            break
        result.append(char)
    return "".join(result)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

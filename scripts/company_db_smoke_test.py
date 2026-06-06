"""End-to-end offline smoke test for the company DB workflow.

This script runs only the existing offline wrapper scripts. It never calls
ai_pm_agent.py, never executes suggested rerun commands, and never uses shell
execution.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TABLES = [
    "companies",
    "tickers",
    "research_runs",
    "pm_decisions",
    "market_snapshots",
    "chokepoint_assessments",
    "evidence_items",
    "facts",
    "import_warnings",
]

EXPECTED_OUTPUTS = [
    "reports/company_dossiers/{ticker}.md",
    "reports/watchlists/top_chokepoints.md",
    "reports/watchlists/latest_decisions.md",
    "reports/data_quality/stale_companies.md",
    "reports/data_quality/warning_summary.md",
    "reports/watchlists/decision_changes.md",
    "reports/refresh/refresh_plan.md",
    "reports/refresh/refresh_queue.csv",
    "reports/approval/approval_packet.md",
    "reports/approval/approval_manifest.csv",
    "reports/approval/manual_rerun_commands.txt",
    "reports/approval/approval_validation.md",
    "reports/approval/approval_validation.csv",
    "reports/approval/approved_commands.txt",
    "reports/approval/approved_manifest_validated.csv",
    "reports/approval/manual_runbook.md",
    "reports/approval/manual_runbook_steps.csv",
]


@dataclass(frozen=True)
class StepResult:
    step: str
    command_or_check: str
    status: str
    elapsed_seconds: float
    output: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "command_or_check": self.command_or_check,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "output": self.output,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SmokeSummary:
    status: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    skipped_steps: int
    total_elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "total_elapsed_seconds": round(self.total_elapsed_seconds, 3),
        }


def summarize_steps(steps: list[StepResult], total_elapsed_seconds: float) -> SmokeSummary:
    failed = sum(1 for step in steps if step.status == "failed")
    skipped = sum(1 for step in steps if step.status == "skipped")
    passed = sum(1 for step in steps if step.status == "passed")
    return SmokeSummary(
        status="passed" if failed == 0 else "failed",
        total_steps=len(steps),
        passed_steps=passed,
        failed_steps=failed,
        skipped_steps=skipped,
        total_elapsed_seconds=total_elapsed_seconds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline company DB workflow smoke test.")
    parser.add_argument("--db", default="data/company_db/company_research.sqlite", help="SQLite DB path.")
    parser.add_argument("--outputs", default="outputs", help="Outputs directory to import.")
    parser.add_argument("--report", required=True, help="Markdown smoke-test report output path.")
    parser.add_argument("--json", required=True, help="JSON smoke-test summary output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    db_path = Path(args.db)
    outputs_dir = Path(args.outputs)
    report_path = Path(args.report)
    json_path = Path(args.json)

    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    steps: list[StepResult] = []
    generated_artifacts: list[str] = []
    warnings: list[str] = []

    def run(step: str, command: list[str], output: str = "") -> None:
        result = run_offline_command(step, command, root)
        steps.append(result)
        if output and result.status == "passed":
            generated_artifacts.append(output)

    py = sys.executable

    run(
        "import_artifacts",
        [py, "scripts/company_db_import.py", "import", "--outputs", str(outputs_dir), "--db", str(db_path)],
    )
    run("db_stats", [py, "scripts/company_db_import.py", "stats", "--db", str(db_path)])
    run("latest_decisions", [py, "scripts/company_db_import.py", "latest", "--db", str(db_path), "--limit", "20"])
    run(
        "chokepoint_ranking",
        [
            py,
            "scripts/company_db_import.py",
            "rank",
            "--db",
            str(db_path),
            "--sort",
            "chokepoint_score",
            "--desc",
            "--limit",
            "20",
        ],
    )

    tickers, ticker_note = choose_dossier_tickers(root / db_path)
    if ticker_note:
        warnings.append(ticker_note)
    if not tickers:
        steps.append(
            StepResult(
                step="sample_dossiers",
                command_or_check="choose dossier tickers",
                status="skipped",
                elapsed_seconds=0.0,
                output="",
                notes="No tickers available for dossier generation.",
            )
        )
    else:
        for ticker in tickers:
            dossier_path = f"reports/company_dossiers/{safe_ticker_file(ticker)}.md"
            run(
                f"dossier_{ticker}",
                [
                    py,
                    "scripts/company_db_report.py",
                    "dossier",
                    "--db",
                    str(db_path),
                    "--ticker",
                    ticker,
                    "--out",
                    dossier_path,
                ],
                dossier_path,
            )

    report_commands = [
        (
            "top_chokepoints_report",
            [
                py,
                "scripts/company_db_report.py",
                "top-chokepoints",
                "--db",
                str(db_path),
                "--limit",
                "25",
                "--out",
                "reports/watchlists/top_chokepoints.md",
            ],
            "reports/watchlists/top_chokepoints.md",
        ),
        (
            "latest_decisions_report",
            [
                py,
                "scripts/company_db_report.py",
                "latest-decisions",
                "--db",
                str(db_path),
                "--limit",
                "50",
                "--out",
                "reports/watchlists/latest_decisions.md",
            ],
            "reports/watchlists/latest_decisions.md",
        ),
        (
            "stale_report",
            [
                py,
                "scripts/company_db_report.py",
                "stale",
                "--db",
                str(db_path),
                "--out",
                "reports/data_quality/stale_companies.md",
            ],
            "reports/data_quality/stale_companies.md",
        ),
        (
            "warnings_report",
            [
                py,
                "scripts/company_db_report.py",
                "warnings",
                "--db",
                str(db_path),
                "--out",
                "reports/data_quality/warning_summary.md",
            ],
            "reports/data_quality/warning_summary.md",
        ),
        (
            "decision_changes_report",
            [
                py,
                "scripts/company_db_report.py",
                "decision-changes",
                "--db",
                str(db_path),
                "--out",
                "reports/watchlists/decision_changes.md",
            ],
            "reports/watchlists/decision_changes.md",
        ),
    ]
    for step, command, output in report_commands:
        run(step, command, output)
    generated_artifacts.extend(
        [
            "reports/exports/top_chokepoints.csv",
            "reports/exports/latest_decisions.csv",
            "reports/exports/stale_companies.csv",
            "reports/exports/warning_summary.csv",
            "reports/exports/decision_changes.csv",
        ]
    )

    run(
        "refresh_plan",
        [
            py,
            "scripts/company_db_refresh.py",
            "plan",
            "--db",
            str(db_path),
            "--out",
            "reports/refresh/refresh_plan.md",
            "--csv",
            "reports/refresh/refresh_queue.csv",
        ],
        "reports/refresh/refresh_plan.md",
    )
    generated_artifacts.append("reports/refresh/refresh_queue.csv")

    run(
        "approval_packet",
        [
            py,
            "scripts/company_db_approval.py",
            "build",
            "--db",
            str(db_path),
            "--out",
            "reports/approval/approval_packet.md",
            "--manifest",
            "reports/approval/approval_manifest.csv",
            "--commands-out",
            "reports/approval/manual_rerun_commands.txt",
            "--limit",
            "25",
        ],
        "reports/approval/approval_packet.md",
    )
    generated_artifacts.extend(["reports/approval/approval_manifest.csv", "reports/approval/manual_rerun_commands.txt"])

    run(
        "approval_validate",
        [
            py,
            "scripts/company_db_approval.py",
            "validate",
            "--db",
            str(db_path),
            "--manifest",
            "reports/approval/approval_manifest.csv",
            "--out",
            "reports/approval/approval_validation.md",
            "--csv",
            "reports/approval/approval_validation.csv",
        ],
        "reports/approval/approval_validation.md",
    )
    generated_artifacts.append("reports/approval/approval_validation.csv")

    run(
        "approval_extract",
        [
            py,
            "scripts/company_db_approval.py",
            "extract-approved",
            "--db",
            str(db_path),
            "--manifest",
            "reports/approval/approval_manifest.csv",
            "--commands-out",
            "reports/approval/approved_commands.txt",
            "--manifest-out",
            "reports/approval/approved_manifest_validated.csv",
            "--validation-out",
            "reports/approval/approval_validation.md",
        ],
        "reports/approval/approved_commands.txt",
    )
    generated_artifacts.append("reports/approval/approved_manifest_validated.csv")

    run(
        "manual_runbook",
        [
            py,
            "scripts/company_db_approval.py",
            "build-runbook",
            "--db",
            str(db_path),
            "--validated-manifest",
            "reports/approval/approved_manifest_validated.csv",
            "--commands",
            "reports/approval/approved_commands.txt",
            "--out",
            "reports/approval/manual_runbook.md",
            "--csv",
            "reports/approval/manual_runbook_steps.csv",
        ],
        "reports/approval/manual_runbook.md",
    )
    generated_artifacts.append("reports/approval/manual_runbook_steps.csv")

    db_health = database_health(root / db_path)
    steps.append(validate_database_health(db_health))
    file_checks = validate_expected_outputs(root, generated_artifacts)
    steps.extend(file_checks)
    approval_state = read_approval_state(root / "reports/approval/approved_manifest_validated.csv")

    elapsed = time.perf_counter() - started
    summary = summarize_steps(steps, elapsed)
    if summary.status == "failed":
        recommendation = "Do not proceed to Phase 3. Fix the failing offline workflow step first."
    else:
        recommendation = (
            "Phase 2 offline research workflow is complete. Stop adding Phase 2 features. "
            "Use the system manually before considering Phase 3."
        )

    report_text = render_report(
        generated_at=generated_at,
        summary=summary,
        steps=steps,
        db_path=str(db_path),
        db_health=db_health,
        generated_artifacts=sorted(set(generated_artifacts + [str(report_path), str(json_path)])),
        approval_state=approval_state,
        warnings=warnings,
        recommendation=recommendation,
    )
    write_text(root / report_path, report_text)
    summary_payload = {
        "generated_at": generated_at,
        "summary": summary.to_dict(),
        "db_path": str(db_path),
        "db_health": db_health,
        "approval_state": approval_state,
        "generated_artifacts": sorted(set(generated_artifacts + [str(report_path), str(json_path)])),
        "warnings": warnings,
        "recommendation": recommendation,
        "steps": [step.to_dict() for step in steps],
    }
    write_json(root / json_path, summary_payload)
    print(
        "offline_smoke_test "
        f"status={summary.status} total_steps={summary.total_steps} passed={summary.passed_steps} "
        f"failed={summary.failed_steps} skipped={summary.skipped_steps} "
        f"report={report_path} json={json_path}"
    )
    return 0 if summary.status == "passed" else 1


def run_offline_command(step: str, command: list[str], cwd: Path) -> StepResult:
    if command_targets_ai_pm_agent(command):
        return StepResult(step, display_command(command), "failed", 0.0, "", "Blocked ai_pm_agent.py execution.")
    start = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, shell=False)
    elapsed = time.perf_counter() - start
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    output = stdout if stdout else stderr
    if stdout and stderr:
        output = stdout + "\n" + stderr
    return StepResult(
        step=step,
        command_or_check=display_command(command),
        status="passed" if completed.returncode == 0 else "failed",
        elapsed_seconds=elapsed,
        output=compact(output, 700),
        notes=f"returncode={completed.returncode}",
    )


def command_targets_ai_pm_agent(command: list[str]) -> bool:
    return any(Path(part).name.lower() == "ai_pm_agent.py" for part in command)


def choose_dossier_tickers(db_path: Path) -> tuple[list[str], str]:
    if not db_path.exists():
        return [], "Database not found before dossier ticker selection."
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT ticker
            FROM research_runs
            WHERE COALESCE(ticker, '') != ''
            ORDER BY ticker
            """
        ).fetchall()
    finally:
        conn.close()
    available = [str(row[0]).upper() for row in rows]
    selected = [ticker for ticker in ("GEV", "AVGO") if ticker in available]
    substitutions: list[str] = []
    for ticker in available:
        if len(selected) >= 2:
            break
        if ticker not in selected:
            selected.append(ticker)
            substitutions.append(ticker)
    note = ""
    if set(selected) != {"GEV", "AVGO"}:
        note = "GEV/AVGO dossier substitution used: " + (", ".join(selected) if selected else "none")
    return selected[:2], note


def database_health(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {table: 0 for table in TABLES}
    conn = sqlite3.connect(db_path)
    try:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in TABLES}
    finally:
        conn.close()


def validate_database_health(health: dict[str, int]) -> StepResult:
    required = ["companies", "research_runs", "pm_decisions", "chokepoint_assessments"]
    missing = [table for table in required if health.get(table, 0) <= 0]
    return StepResult(
        step="database_health_check",
        command_or_check="nonzero companies/research_runs/pm_decisions/chokepoint_assessments",
        status="failed" if missing else "passed",
        elapsed_seconds=0.0,
        output=", ".join(f"{table}={health.get(table, 0)}" for table in required),
        notes="missing=" + ",".join(missing) if missing else "required DB counts are nonzero",
    )


def validate_expected_outputs(root: Path, paths: list[str]) -> list[StepResult]:
    results: list[StepResult] = []
    for rel_path in sorted(set(paths)):
        path = root / rel_path
        if path.exists() and path.stat().st_size > 0:
            status = "passed"
            notes = f"bytes={path.stat().st_size}"
        elif path.exists():
            status = "failed"
            notes = "file exists but is empty"
        else:
            status = "failed"
            notes = "file missing"
        results.append(
            StepResult(
                step=f"file_check:{rel_path}",
                command_or_check=f"non-empty file {rel_path}",
                status=status,
                elapsed_seconds=0.0,
                output=rel_path,
                notes=notes,
            )
        )
    return results


def read_approval_state(validated_manifest: Path) -> dict[str, int]:
    state = {
        "approval_manifest_rows": 0,
        "approved_rows": 0,
        "valid_approved_commands": 0,
        "invalid_approved_rows": 0,
        "ambiguous_approval_rows": 0,
        "not_approved_rows": 0,
    }
    if not validated_manifest.exists():
        return state
    import csv

    with validated_manifest.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            state["approval_manifest_rows"] += 1
            approved = (row.get("approved") or "").strip().lower()
            status = (row.get("validation_status") or "").strip()
            if approved in {"true", "yes", "y", "1", "approve", "approved", "x"}:
                state["approved_rows"] += 1
            if status == "valid_approved":
                state["valid_approved_commands"] += 1
            elif status == "invalid_approved":
                state["invalid_approved_rows"] += 1
            elif status == "ambiguous_approval":
                state["ambiguous_approval_rows"] += 1
            elif status == "not_approved":
                state["not_approved_rows"] += 1
    return state


def render_report(
    generated_at: str,
    summary: SmokeSummary,
    steps: list[StepResult],
    db_path: str,
    db_health: dict[str, int],
    generated_artifacts: list[str],
    approval_state: dict[str, int],
    warnings: list[str],
    recommendation: str,
) -> str:
    failures = [step for step in steps if step.status == "failed"]
    warning_lines = list(warnings)
    warning_lines.extend(f"{step.step}: {step.notes}" for step in failures)
    if not warning_lines:
        warning_lines.append("No failures or abnormal warnings.")
    if approval_state.get("valid_approved_commands", 0) == 0:
        zero_note = "Expected zero-approved behavior: no approved commands were extracted."
    else:
        zero_note = "Approved command extraction produced valid approved commands."
    lines = [
        "# Offline Workflow Smoke Test Report",
        "",
        "## 1. Summary",
        "",
        bullet_list(
            [
                f"Generated: {generated_at}",
                f"Status: {summary.status}",
                f"Total steps: {summary.total_steps}",
                f"Passed steps: {summary.passed_steps}",
                f"Failed steps: {summary.failed_steps}",
                f"Skipped steps: {summary.skipped_steps}",
                f"Total elapsed seconds: {summary.total_elapsed_seconds:.3f}",
                f"DB path: `{db_path}`",
            ]
        ),
        "",
        "## 2. Step Results",
        "",
        table(
            ["step", "command or check", "status", "elapsed_seconds", "output", "notes"],
            [
                [
                    step.step,
                    step.command_or_check,
                    step.status,
                    f"{step.elapsed_seconds:.3f}",
                    step.output,
                    step.notes,
                ]
                for step in steps
            ],
        ),
        "",
        "## 3. Database Health",
        "",
        table(["table", "count"], [[table_name, db_health.get(table_name, 0)] for table_name in TABLES]),
        "",
        "## 4. Generated Artifacts",
        "",
        bullet_list(f"`{path}`" for path in generated_artifacts),
        "",
        "## 5. Approval State",
        "",
        table(["metric", "count"], [[key, value] for key, value in approval_state.items()]),
        "",
        zero_note,
        "",
        "## 6. Failures / Warnings",
        "",
        bullet_list(warning_lines),
        "",
        "## 7. Final Recommendation",
        "",
        recommendation,
        "",
    ]
    return "\n".join(lines)


def table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
    for row in rows:
        lines.append(" | ".join(markdown_cell(value) for value in row))
    return "\n".join(lines)


def bullet_list(items: Any) -> str:
    values = [str(item) for item in items if str(item)]
    return "\n".join(f"- {item}" for item in values) if values else "- N/A"


def markdown_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("|", "/")


def display_command(command: list[str]) -> str:
    parts = []
    for part in command:
        text = str(part)
        if Path(text).name.lower().startswith("python") and text == sys.executable:
            parts.append("python")
        else:
            parts.append(text)
    return " ".join(parts)


def compact(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def safe_ticker_file(ticker: str) -> str:
    return ticker.replace(".", "_")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

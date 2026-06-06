"""Schema initialization helpers for the company research database."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .schema import SCHEMA_STATEMENTS, SCHEMA_VERSION


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with the expected pragmas enabled."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create all Phase 1 tables if they do not already exist."""

    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_VERSION, "phase1_company_research_schema", utc_now()),
    )
    conn.commit()

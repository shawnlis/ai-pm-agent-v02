"""SQLite repository for the fixture-first SEC / IR evidence database."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("reports") / "sec_ir_evidence_db" / "fixture_mvp" / "evidence_db.sqlite"

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS companies (
        company_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        company_name TEXT NOT NULL,
        cik TEXT NOT NULL,
        cik_padded TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT '',
        source_level TEXT NOT NULL DEFAULT 'Level 0',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_documents (
        document_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        source_date TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        confidence TEXT NOT NULL,
        fixture_only INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(company_id) REFERENCES companies(company_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sec_filings (
        filing_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        source_document_id TEXT NOT NULL,
        accession_number TEXT NOT NULL,
        form TEXT NOT NULL,
        filing_date TEXT NOT NULL,
        report_date TEXT NOT NULL,
        primary_document TEXT NOT NULL,
        source_url TEXT NOT NULL,
        confidence TEXT NOT NULL,
        fixture_only INTEGER NOT NULL,
        FOREIGN KEY(company_id) REFERENCES companies(company_id),
        FOREIGN KEY(source_document_id) REFERENCES source_documents(document_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xbrl_facts (
        fact_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        source_document_id TEXT NOT NULL,
        taxonomy TEXT NOT NULL,
        concept TEXT NOT NULL,
        label TEXT NOT NULL,
        unit TEXT NOT NULL,
        value REAL NOT NULL,
        end_date TEXT NOT NULL,
        filed_date TEXT NOT NULL,
        frame TEXT NOT NULL,
        accession_number TEXT NOT NULL,
        form TEXT NOT NULL,
        fiscal_year INTEGER,
        fiscal_period TEXT NOT NULL,
        confidence TEXT NOT NULL,
        fixture_only INTEGER NOT NULL,
        FOREIGN KEY(company_id) REFERENCES companies(company_id),
        FOREIGN KEY(source_document_id) REFERENCES source_documents(document_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_claims (
        claim_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        source_document_id TEXT NOT NULL,
        fact_id TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        claim_text TEXT NOT NULL,
        source_date TEXT NOT NULL,
        confidence TEXT NOT NULL,
        review_status TEXT NOT NULL,
        fixture_only INTEGER NOT NULL,
        FOREIGN KEY(company_id) REFERENCES companies(company_id),
        FOREIGN KEY(source_document_id) REFERENCES source_documents(document_id),
        FOREIGN KEY(fact_id) REFERENCES xbrl_facts(fact_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingestion_runs (
        run_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        company_name TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        source_mode TEXT NOT NULL,
        fixture_only INTEGER NOT NULL,
        status TEXT NOT NULL,
        warnings_count INTEGER NOT NULL,
        errors_count INTEGER NOT NULL,
        output_dir TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingestion_warnings (
        warning_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        code TEXT NOT NULL,
        message TEXT NOT NULL,
        source_path TEXT NOT NULL,
        context_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES ingestion_runs(run_id)
    )
    """,
]


def connect(db_path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(f"SQLite database does not exist: {path}")
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()


class EvidenceRepository:
    """Small SQLite boundary for fixture-first evidence records."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, read_only: bool = False):
        self.db_path = Path(db_path)
        self.read_only = read_only
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> "EvidenceRepository":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        self.conn = connect(self.db_path, read_only=self.read_only)
        if not self.read_only:
            initialize_schema(self.conn)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def commit(self) -> None:
        self._conn().commit()

    def insert_company(self, values: Any) -> None:
        self._upsert("companies", self._row(values), "company_id")

    def insert_source_document(self, values: Any) -> None:
        self._upsert("source_documents", self._row(values), "document_id")

    def insert_sec_filing(self, values: Any) -> None:
        self._upsert("sec_filings", self._row(values), "filing_id")

    def insert_xbrl_fact(self, values: Any) -> None:
        self._upsert("xbrl_facts", self._row(values), "fact_id")

    def insert_evidence_claim(self, values: Any) -> None:
        self._upsert("evidence_claims", self._row(values), "claim_id")

    def insert_ingestion_run(self, values: Any) -> None:
        self._upsert("ingestion_runs", self._row(values), "run_id")

    def insert_ingestion_warning(self, values: Any) -> None:
        self._upsert("ingestion_warnings", self._row(values), "warning_id")

    def table_count(self, table: str) -> int:
        allowed = {
            "companies",
            "source_documents",
            "sec_filings",
            "xbrl_facts",
            "evidence_claims",
            "ingestion_runs",
            "ingestion_warnings",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported evidence DB table: {table}")
        row = self._conn().execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self._conn().execute(sql, params))

    def summarize_counts(self) -> dict[str, int]:
        tables = [
            "companies",
            "source_documents",
            "sec_filings",
            "xbrl_facts",
            "evidence_claims",
            "ingestion_runs",
            "ingestion_warnings",
        ]
        return {table: self.table_count(table) for table in tables}

    def _upsert(self, table: str, values: dict[str, Any], pk: str) -> None:
        values = {key: self._sqlite_value(value) for key, value in values.items()}
        columns = list(values)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column} = excluded.{column}" for column in columns if column != pk)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
        )
        self._conn().execute(sql, tuple(values[column] for column in columns))

    def _conn(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("EvidenceRepository is not open")
        return self.conn

    @staticmethod
    def _row(values: Any) -> dict[str, Any]:
        if is_dataclass(values):
            return asdict(values)
        return dict(values)

    @staticmethod
    def _sqlite_value(value: Any) -> Any:
        if isinstance(value, bool):
            return 1 if value else 0
        return value

"""Repository boundary for the company research SQLite database."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path
from typing import Any

from .migrations import connect, initialize_schema


@dataclass(frozen=True)
class DecisionFilters:
    """Optional filters for latest-decision query views."""

    ticker: str | None = None
    market: str | None = None
    action: str | None = None
    rating: str | None = None
    min_chokepoint_score: float | None = None
    max_chokepoint_score: float | None = None
    min_pm_score: float | None = None
    max_pm_score: float | None = None
    has_warnings: bool | None = None
    missing_evidence: bool | None = None


class CompanyResearchRepository:
    """Small SQLite repository with idempotent upsert operations."""

    def __init__(self, db_path: Path | str, read_only: bool = False):
        self.db_path = Path(db_path)
        self.read_only = read_only
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> "CompanyResearchRepository":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        if self.read_only:
            if not self.db_path.exists():
                raise FileNotFoundError(f"SQLite database does not exist: {self.db_path}")
            uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            return
        self.conn = connect(self.db_path)
        initialize_schema(self.conn)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def commit(self) -> None:
        self._conn().commit()

    def upsert_company(self, values: dict[str, Any]) -> None:
        self._upsert("companies", values, "company_id")

    def upsert_ticker(self, values: dict[str, Any]) -> None:
        self._upsert("tickers", values, "ticker_id")

    def upsert_research_run(self, values: dict[str, Any]) -> None:
        self._upsert("research_runs", values, "run_id")

    def upsert_market_snapshot(self, values: dict[str, Any]) -> None:
        self._upsert("market_snapshots", values, "snapshot_id")

    def upsert_pm_decision(self, values: dict[str, Any]) -> None:
        self._upsert("pm_decisions", values, "decision_id")

    def upsert_chokepoint_assessment(self, values: dict[str, Any]) -> None:
        self._upsert("chokepoint_assessments", values, "assessment_id")

    def upsert_artifact_file(self, values: dict[str, Any]) -> None:
        self._upsert("artifact_files", values, "artifact_file_id")

    def replace_evidence_items(self, run_id: str, source_file: str, rows: list[dict[str, Any]]) -> None:
        conn = self._conn()
        conn.execute(
            "DELETE FROM evidence_items WHERE run_id = ? AND source_file = ?",
            (run_id, source_file),
        )
        for row in rows:
            self._upsert("evidence_items", row, "evidence_id")

    def replace_facts(self, run_id: str, source_file: str, rows: list[dict[str, Any]]) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM facts WHERE run_id = ? AND source_file = ?", (run_id, source_file))
        for row in rows:
            self._upsert("facts", row, "fact_id")

    def add_warning(self, values: dict[str, Any]) -> None:
        columns = list(values)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT OR IGNORE INTO import_warnings ({', '.join(columns)}) VALUES ({placeholders})"
        self._conn().execute(sql, tuple(values[column] for column in columns))

    def list_companies(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                """
                SELECT
                    c.company_id,
                    c.canonical_name AS company,
                    t.ticker,
                    t.market,
                    COUNT(rr.run_id) AS run_count,
                    MAX(COALESCE(rr.run_created_at, rr.imported_at)) AS latest_run_date
                FROM companies c
                LEFT JOIN tickers t ON t.company_id = c.company_id
                LEFT JOIN research_runs rr ON rr.company_id = c.company_id
                GROUP BY c.company_id, c.canonical_name, t.ticker, t.market
                ORDER BY LOWER(c.canonical_name), t.ticker
                LIMIT ?
                """,
                (limit,),
            )
        )

    def list_latest_decisions(self, limit: int = 25) -> list[sqlite3.Row]:
        return self.filter_decisions(limit=limit)

    def get_company_by_ticker(self, ticker: str) -> sqlite3.Row | None:
        rows = list(
            self._conn().execute(
                """
                SELECT
                    c.company_id,
                    c.canonical_name AS company,
                    t.ticker,
                    t.market,
                    t.financial_ticker,
                    COUNT(rr.run_id) AS run_count,
                    MAX(COALESCE(rr.run_created_at, rr.imported_at)) AS latest_run_date
                FROM tickers t
                JOIN companies c ON c.company_id = t.company_id
                LEFT JOIN research_runs rr ON rr.ticker_id = t.ticker_id
                WHERE UPPER(t.ticker_norm) = ?
                GROUP BY c.company_id, c.canonical_name, t.ticker, t.market, t.financial_ticker
                ORDER BY latest_run_date DESC
                LIMIT 1
                """,
                (ticker.strip().upper(),),
            )
        )
        return rows[0] if rows else None

    def get_runs_for_ticker(self, ticker: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.compare_ticker_history(ticker=ticker, limit=limit)

    def get_latest_run_for_ticker(self, ticker: str) -> sqlite3.Row | None:
        rows = self.get_runs_for_ticker(ticker=ticker, limit=1)
        return rows[0] if rows else None

    def get_latest_decision_for_ticker(self, ticker: str) -> sqlite3.Row | None:
        rows = self.filter_decisions(filters=DecisionFilters(ticker=ticker), limit=1)
        return rows[0] if rows else None

    def get_company_decisions(self, ticker: str, limit: int = 10) -> list[sqlite3.Row]:
        return self.get_runs_for_ticker(ticker=ticker, limit=limit)

    def filter_decisions(
        self,
        filters: DecisionFilters | None = None,
        limit: int = 25,
        sort: str = "latest_run_date",
        desc: bool = True,
    ) -> list[sqlite3.Row]:
        filters = filters or DecisionFilters()
        where, params = self._decision_filter_sql(filters)
        order_by = self._decision_order_clause(sort, desc)
        sql = (
            self._latest_decision_cte()
            + f"""
            SELECT
                run_id,
                ticker,
                company_name,
                market,
                action,
                rating,
                pm_score,
                chokepoint_score,
                confidence,
                latest_run_date,
                suggested_position_pct,
                artifact_dir,
                evidence_level,
                warning_count,
                evidence_count,
                facts_count,
                missing_artifacts,
                has_market_snapshot,
                has_pm_decision,
                has_chokepoint_assessment
            FROM latest
            WHERE rn = 1 {where}
            {order_by}
            LIMIT ?
            """
        )
        return list(self._conn().execute(sql, (*params, limit)))

    def get_latest_report_row_for_ticker(self, ticker: str) -> sqlite3.Row | None:
        rows = self.filter_decisions(filters=DecisionFilters(ticker=ticker), limit=1)
        return rows[0] if rows else None

    def get_pm_decision_for_run(self, run_id: str) -> sqlite3.Row | None:
        return self._fetch_one("SELECT * FROM pm_decisions WHERE run_id = ?", (run_id,))

    def get_market_snapshot_for_run(self, run_id: str) -> sqlite3.Row | None:
        return self._fetch_one("SELECT * FROM market_snapshots WHERE run_id = ?", (run_id,))

    def get_chokepoint_assessment_for_run(self, run_id: str) -> sqlite3.Row | None:
        return self._fetch_one("SELECT * FROM chokepoint_assessments WHERE run_id = ?", (run_id,))

    def list_evidence_for_run(self, run_id: str, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                """
                SELECT *
                FROM evidence_items
                WHERE run_id = ?
                ORDER BY
                    CASE evidence_tier
                        WHEN 'primary' THEN 1
                        WHEN 'primary_supported' THEN 2
                        WHEN 'secondary_supported' THEN 3
                        ELSE 9
                    END,
                    ordinal
                LIMIT ?
                """,
                (run_id, limit),
            )
        )

    def list_facts_for_run(self, run_id: str, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                """
                SELECT *
                FROM facts
                WHERE run_id = ?
                ORDER BY confidence IS NULL, confidence DESC, ordinal
                LIMIT ?
                """,
                (run_id, limit),
            )
        )

    def list_warnings_for_run(self, run_id: str, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                """
                SELECT *
                FROM import_warnings
                WHERE run_id = ?
                ORDER BY warning_type, message
                LIMIT ?
                """,
                (run_id, limit),
            )
        )

    def count_facts_for_run(self, run_id: str) -> int:
        row = self._conn().execute("SELECT COUNT(*) AS count FROM facts WHERE run_id = ?", (run_id,)).fetchone()
        return int(row["count"])

    def count_evidence_for_run(self, run_id: str) -> int:
        row = self._conn().execute(
            "SELECT COUNT(*) AS count FROM evidence_items WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["count"])

    def list_decision_changes(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                """
                WITH history AS (
                    SELECT
                        rr.ticker,
                        rr.company_name,
                        rr.market,
                        rr.run_created_at,
                        rr.artifact_dir,
                        pd.action,
                        pd.rating,
                        pd.weighted_investment_score AS pm_score,
                        ca.chokepoint_score,
                        LAG(pd.action) OVER (
                            PARTITION BY UPPER(rr.ticker)
                            ORDER BY COALESCE(rr.run_created_at, rr.imported_at), rr.artifact_dir
                        ) AS previous_action,
                        LAG(pd.rating) OVER (
                            PARTITION BY UPPER(rr.ticker)
                            ORDER BY COALESCE(rr.run_created_at, rr.imported_at), rr.artifact_dir
                        ) AS previous_rating,
                        LAG(pd.weighted_investment_score) OVER (
                            PARTITION BY UPPER(rr.ticker)
                            ORDER BY COALESCE(rr.run_created_at, rr.imported_at), rr.artifact_dir
                        ) AS previous_pm_score,
                        LAG(ca.chokepoint_score) OVER (
                            PARTITION BY UPPER(rr.ticker)
                            ORDER BY COALESCE(rr.run_created_at, rr.imported_at), rr.artifact_dir
                        ) AS previous_chokepoint_score,
                        LAG(rr.run_created_at) OVER (
                            PARTITION BY UPPER(rr.ticker)
                            ORDER BY COALESCE(rr.run_created_at, rr.imported_at), rr.artifact_dir
                        ) AS previous_run_date
                    FROM research_runs rr
                    LEFT JOIN pm_decisions pd ON pd.run_id = rr.run_id
                    LEFT JOIN chokepoint_assessments ca ON ca.run_id = rr.run_id
                )
                SELECT
                    ticker,
                    company_name,
                    market,
                    previous_run_date,
                    run_created_at AS latest_run_date,
                    previous_action,
                    action,
                    previous_rating,
                    rating,
                    previous_pm_score,
                    pm_score,
                    CASE
                        WHEN previous_pm_score IS NULL OR pm_score IS NULL THEN NULL
                        ELSE pm_score - previous_pm_score
                    END AS pm_score_change,
                    previous_chokepoint_score,
                    chokepoint_score,
                    CASE
                        WHEN previous_chokepoint_score IS NULL OR chokepoint_score IS NULL THEN NULL
                        ELSE chokepoint_score - previous_chokepoint_score
                    END AS chokepoint_score_change,
                    artifact_dir
                FROM history
                WHERE previous_run_date IS NOT NULL
                  AND (
                    COALESCE(previous_action, '') != COALESCE(action, '')
                    OR COALESCE(previous_rating, '') != COALESCE(rating, '')
                    OR COALESCE(previous_pm_score, -999999.0) != COALESCE(pm_score, -999999.0)
                    OR COALESCE(previous_chokepoint_score, -999999.0) != COALESCE(chokepoint_score, -999999.0)
                  )
                ORDER BY latest_run_date DESC, ticker
                LIMIT ?
                """,
                (limit,),
            )
        )

    def compare_ticker_history(self, ticker: str, limit: int = 50) -> list[sqlite3.Row]:
        ticker_norm = ticker.strip().upper()
        return list(
            self._conn().execute(
                """
                SELECT
                    rr.run_id,
                    rr.ticker,
                    rr.company_name,
                    rr.market,
                    pd.action,
                    pd.rating,
                    pd.weighted_investment_score AS pm_score,
                    ca.chokepoint_score,
                    pd.suggested_position_pct,
                    pd.confidence_score AS confidence,
                    pd.final_pm_judgment,
                    rr.run_created_at AS latest_run_date,
                    rr.artifact_dir
                FROM research_runs rr
                LEFT JOIN pm_decisions pd ON pd.run_id = rr.run_id
                LEFT JOIN chokepoint_assessments ca ON ca.run_id = rr.run_id
                WHERE UPPER(rr.ticker) = ?
                ORDER BY COALESCE(rr.run_created_at, rr.imported_at) DESC, rr.artifact_dir DESC
                LIMIT ?
                """,
                (ticker_norm, limit),
            )
        )

    def rank_by_chokepoint_score(self, limit: int = 25, desc: bool = True) -> list[sqlite3.Row]:
        return self.filter_decisions(limit=limit, sort="chokepoint_score", desc=desc)

    def rank_by_pm_score(self, limit: int = 25, desc: bool = True) -> list[sqlite3.Row]:
        return self.filter_decisions(limit=limit, sort="pm_score", desc=desc)

    def list_import_warnings(
        self,
        limit: int = 50,
        ticker: str | None = None,
        warning_type: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("UPPER(rr.ticker) = ?")
            params.append(ticker.strip().upper())
        if warning_type:
            clauses.append("iw.warning_type = ?")
            params.append(warning_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return list(
            self._conn().execute(
                f"""
                SELECT
                    iw.warning_type,
                    iw.message,
                    rr.ticker,
                    rr.company_name,
                    rr.run_created_at AS latest_run_date,
                    iw.artifact_path,
                    rr.artifact_dir
                FROM import_warnings iw
                LEFT JOIN research_runs rr ON rr.run_id = iw.run_id
                {where}
                ORDER BY COALESCE(rr.run_created_at, iw.created_at) DESC, iw.warning_type, iw.message
                LIMIT ?
                """,
                (*params, limit),
            )
        )

    def summarize_database(self) -> dict[str, Any]:
        tables = [
            "companies",
            "tickers",
            "research_runs",
            "market_snapshots",
            "pm_decisions",
            "chokepoint_assessments",
            "evidence_items",
            "facts",
            "artifact_files",
            "import_warnings",
        ]
        counts = {table: self.table_count(table) for table in tables}
        warning_rows = self._conn().execute(
            """
            SELECT warning_type, COUNT(*) AS count
            FROM import_warnings
            GROUP BY warning_type
            ORDER BY warning_type
            """
        )
        return {
            "counts": counts,
            "warning_types": {row["warning_type"]: int(row["count"]) for row in warning_rows},
        }

    def list_stale_or_incomplete_companies(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self._conn().execute(
                self._latest_decision_cte()
                + """
                SELECT
                    ticker,
                    company_name,
                    market,
                    latest_run_date,
                    missing_artifacts,
                    warning_count,
                    has_market_snapshot,
                    has_pm_decision,
                    has_chokepoint_assessment,
                    evidence_count,
                    facts_count
                FROM latest
                WHERE rn = 1
                  AND (
                    warning_count > 0
                    OR has_market_snapshot = 0
                    OR has_pm_decision = 0
                    OR has_chokepoint_assessment = 0
                    OR evidence_count = 0
                    OR facts_count = 0
                  )
                ORDER BY warning_count DESC, latest_run_date DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    def table_count(self, table: str) -> int:
        allowed = {
            "companies",
            "tickers",
            "research_runs",
            "market_snapshots",
            "evidence_items",
            "facts",
            "chokepoint_assessments",
            "pm_decisions",
            "artifact_files",
            "import_warnings",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        row = self._conn().execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def _decision_filter_sql(self, filters: DecisionFilters) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.ticker:
            clauses.append("UPPER(ticker) = ?")
            params.append(filters.ticker.strip().upper())
        if filters.market:
            clauses.append("LOWER(COALESCE(market, '')) = LOWER(?)")
            params.append(filters.market.strip())
        if filters.action:
            clauses.append("LOWER(COALESCE(action, '')) = LOWER(?)")
            params.append(filters.action.strip())
        if filters.rating:
            clauses.append("LOWER(COALESCE(rating, '')) = LOWER(?)")
            params.append(filters.rating.strip())
        if filters.min_chokepoint_score is not None:
            clauses.append("chokepoint_score >= ?")
            params.append(filters.min_chokepoint_score)
        if filters.max_chokepoint_score is not None:
            clauses.append("chokepoint_score <= ?")
            params.append(filters.max_chokepoint_score)
        if filters.min_pm_score is not None:
            clauses.append("pm_score >= ?")
            params.append(filters.min_pm_score)
        if filters.max_pm_score is not None:
            clauses.append("pm_score <= ?")
            params.append(filters.max_pm_score)
        if filters.has_warnings is True:
            clauses.append("warning_count > 0")
        elif filters.has_warnings is False:
            clauses.append("warning_count = 0")
        if filters.missing_evidence is True:
            clauses.append("evidence_count = 0")
        elif filters.missing_evidence is False:
            clauses.append("evidence_count > 0")
        if not clauses:
            return "", params
        return " AND " + " AND ".join(clauses), params

    def _latest_decision_cte(self) -> str:
        return """
            WITH warning_counts AS (
                SELECT run_id, COUNT(*) AS warning_count
                FROM import_warnings
                GROUP BY run_id
            ),
            missing_artifacts AS (
                SELECT
                    run_id,
                    GROUP_CONCAT(REPLACE(message, 'Optional artifact is missing: ', ''), ', ') AS missing_artifacts
                FROM import_warnings
                WHERE warning_type = 'missing_optional_artifact'
                GROUP BY run_id
            ),
            evidence_counts AS (
                SELECT run_id, COUNT(*) AS evidence_count
                FROM evidence_items
                GROUP BY run_id
            ),
            fact_counts AS (
                SELECT run_id, COUNT(*) AS facts_count
                FROM facts
                GROUP BY run_id
            ),
            latest AS (
                SELECT
                    rr.run_id,
                    rr.ticker,
                    rr.company_name,
                    rr.market,
                    pd.action,
                    pd.rating,
                    pd.weighted_investment_score AS pm_score,
                    ca.chokepoint_score,
                    ca.evidence_level,
                    pd.confidence_score AS confidence,
                    pd.suggested_position_pct,
                    rr.run_created_at AS latest_run_date,
                    rr.imported_at,
                    rr.artifact_dir,
                    COALESCE(w.warning_count, 0) AS warning_count,
                    COALESCE(e.evidence_count, 0) AS evidence_count,
                    COALESCE(f.facts_count, 0) AS facts_count,
                    COALESCE(m.missing_artifacts, '') AS missing_artifacts,
                    CASE WHEN ms.run_id IS NULL THEN 0 ELSE 1 END AS has_market_snapshot,
                    CASE WHEN pd.run_id IS NULL THEN 0 ELSE 1 END AS has_pm_decision,
                    CASE WHEN ca.run_id IS NULL THEN 0 ELSE 1 END AS has_chokepoint_assessment,
                    ROW_NUMBER() OVER (
                        PARTITION BY UPPER(COALESCE(rr.ticker, ''))
                        ORDER BY COALESCE(rr.run_created_at, rr.imported_at) DESC, rr.artifact_dir DESC
                    ) AS rn
                FROM research_runs rr
                LEFT JOIN pm_decisions pd ON pd.run_id = rr.run_id
                LEFT JOIN chokepoint_assessments ca ON ca.run_id = rr.run_id
                LEFT JOIN market_snapshots ms ON ms.run_id = rr.run_id
                LEFT JOIN warning_counts w ON w.run_id = rr.run_id
                LEFT JOIN evidence_counts e ON e.run_id = rr.run_id
                LEFT JOIN fact_counts f ON f.run_id = rr.run_id
                LEFT JOIN missing_artifacts m ON m.run_id = rr.run_id
            )
        """

    def _decision_order_clause(self, sort: str, desc: bool) -> str:
        sort_columns = {
            "ticker": "ticker",
            "company": "company_name",
            "company_name": "company_name",
            "market": "market",
            "action": "action",
            "rating": "rating",
            "pm_score": "pm_score",
            "chokepoint_score": "chokepoint_score",
            "confidence": "confidence",
            "latest_run_date": "latest_run_date",
            "warning_count": "warning_count",
        }
        column = sort_columns.get(sort, "latest_run_date")
        direction = "DESC" if desc else "ASC"
        return f"ORDER BY {column} IS NULL, {column} {direction}, ticker ASC"

    def _upsert(self, table: str, values: dict[str, Any], pk: str) -> None:
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
            raise RuntimeError("Repository is not open")
        return self.conn

    def _fetch_one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        rows = list(self._conn().execute(sql, params))
        return rows[0] if rows else None

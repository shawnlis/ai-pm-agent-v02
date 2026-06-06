-- Schema-only export for local company_research.sqlite.
-- No row data is included.

-- index: idx_evidence_url
CREATE INDEX idx_evidence_url ON evidence_items(url);

-- index: idx_facts_source_url
CREATE INDEX idx_facts_source_url ON facts(source_url);

-- index: idx_import_warnings_run
CREATE INDEX idx_import_warnings_run ON import_warnings(run_id);

-- index: idx_pm_decisions_action
CREATE INDEX idx_pm_decisions_action ON pm_decisions(action);

-- index: idx_pm_decisions_rating
CREATE INDEX idx_pm_decisions_rating ON pm_decisions(rating);

-- index: idx_research_runs_company
CREATE INDEX idx_research_runs_company ON research_runs(company_id);

-- index: idx_research_runs_created
CREATE INDEX idx_research_runs_created ON research_runs(run_created_at);

-- index: idx_research_runs_ticker
CREATE INDEX idx_research_runs_ticker ON research_runs(ticker);

-- table: artifact_files
CREATE TABLE artifact_files (
        artifact_file_id TEXT PRIMARY KEY,
        run_id TEXT,
        artifact_path TEXT NOT NULL,
        artifact_path_rel TEXT,
        file_type TEXT NOT NULL,
        sha256 TEXT,
        size_bytes INTEGER,
        modified_at TEXT,
        imported_at TEXT NOT NULL,
        UNIQUE(run_id, artifact_path),
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: chokepoint_assessments
CREATE TABLE chokepoint_assessments (
        assessment_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        chokepoint_score REAL,
        indispensability_score REAL,
        scarcity_score REAL,
        customer_validation_score REAL,
        nvidia_signal_score REAL,
        substitution_risk_score REAL,
        timing_risk_score REAL,
        market_awareness_score REAL,
        valuation_risk_score REAL,
        serenity_thesis_quality TEXT,
        evidence_level TEXT,
        deep_research_priority TEXT,
        scout_recommendation TEXT,
        overlay_applied INTEGER,
        overlay_reason TEXT,
        overlay_warnings_json TEXT,
        raw_json TEXT,
        imported_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: companies
CREATE TABLE companies (
        company_id TEXT PRIMARY KEY,
        canonical_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(canonical_name)
    );

-- table: evidence_items
CREATE TABLE evidence_items (
        evidence_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        source_file TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        provider TEXT,
        query_type TEXT,
        expected_tier TEXT,
        evidence_tier TEXT,
        source_type TEXT,
        source_domain TEXT,
        title TEXT,
        url TEXT,
        snippet TEXT,
        raw_text TEXT,
        imported_at TEXT NOT NULL,
        UNIQUE(run_id, source_file, ordinal),
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: facts
CREATE TABLE facts (
        fact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        source_file TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        ticker TEXT,
        company_name TEXT,
        theme TEXT,
        market TEXT,
        fact TEXT,
        fact_category TEXT,
        source_url TEXT,
        source_domain TEXT,
        evidence_tier TEXT,
        source_type TEXT,
        title TEXT,
        snippet TEXT,
        confidence REAL,
        query_type TEXT,
        provider TEXT,
        model_used TEXT,
        fetched_at TEXT,
        source_published_at TEXT,
        expires_at TEXT,
        raw_json TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        UNIQUE(run_id, source_file, ordinal),
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: import_warnings
CREATE TABLE import_warnings (
        warning_id TEXT PRIMARY KEY,
        run_id TEXT,
        artifact_path TEXT,
        warning_type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(run_id, artifact_path, warning_type, message),
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: market_snapshots
CREATE TABLE market_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        ticker TEXT,
        financial_ticker TEXT,
        short_name TEXT,
        long_name TEXT,
        sector TEXT,
        industry TEXT,
        country TEXT,
        currency TEXT,
        financial_currency TEXT,
        latest_price REAL,
        market_cap REAL,
        enterprise_value REAL,
        trailing_pe REAL,
        forward_pe REAL,
        price_to_sales REAL,
        price_to_book REAL,
        ev_to_revenue REAL,
        ev_to_ebitda REAL,
        one_year_return REAL,
        volatility_1y REAL,
        max_drawdown_2y REAL,
        trend_label TEXT,
        market_data_reliability TEXT,
        financial_statement_reliability TEXT,
        price_data_reliability_from_fetch TEXT,
        raw_json TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: pm_decisions
CREATE TABLE pm_decisions (
        decision_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        ticker TEXT,
        company_name TEXT,
        rating TEXT,
        action TEXT,
        suggested_position_pct REAL,
        confidence_score REAL,
        risk_score REAL,
        evidence_quality_score REAL,
        valuation_attractiveness_score REAL,
        weighted_investment_score REAL,
        chokepoint_adjusted_score REAL,
        thesis_summary TEXT,
        final_pm_judgment TEXT,
        valuation_view TEXT,
        valuation_is_justified INTEGER,
        raw_json TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES research_runs(run_id) ON DELETE CASCADE
    );

-- table: research_runs
CREATE TABLE research_runs (
        run_id TEXT PRIMARY KEY,
        artifact_dir TEXT NOT NULL UNIQUE,
        artifact_dir_rel TEXT,
        ticker_id TEXT,
        company_id TEXT,
        ticker TEXT,
        company_name TEXT,
        market TEXT,
        theme TEXT,
        run_created_at TEXT,
        imported_at TEXT NOT NULL,
        source_modified_at TEXT,
        pm_decision_path TEXT,
        status TEXT NOT NULL DEFAULT 'imported',
        research_log_row_json TEXT,
        raw_metadata_json TEXT,
        FOREIGN KEY(ticker_id) REFERENCES tickers(ticker_id) ON DELETE SET NULL,
        FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE SET NULL
    );

-- table: schema_migrations
CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    );

-- table: tickers
CREATE TABLE tickers (
        ticker_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        ticker_norm TEXT NOT NULL,
        market TEXT NOT NULL DEFAULT '',
        financial_ticker TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(ticker_norm, market),
        FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE
    );

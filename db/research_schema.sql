-- Research Orchestration Module - Database Schema

-- Research runs (parallel to evolution runs)
CREATE TABLE IF NOT EXISTS research_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    phase TEXT NOT NULL DEFAULT 'QUEUED',
    project TEXT DEFAULT 'onjaro',
    items_total INTEGER DEFAULT 0,
    items_completed INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0,
    trigger_type TEXT DEFAULT 'scheduled',
    error_message TEXT
);

-- Research event log (audit trail)
CREATE TABLE IF NOT EXISTS research_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    phase TEXT,
    agent_name TEXT,
    severity TEXT DEFAULT 'INFO',
    event_type TEXT,
    message TEXT,
    data_json TEXT,
    duration_ms INTEGER,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
);

-- Per-item tracking within a run
CREATE TABLE IF NOT EXISTS research_items_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    phase TEXT DEFAULT 'QUEUED',
    raw_findings_count INTEGER DEFAULT 0,
    extracted_count INTEGER DEFAULT 0,
    validated_count INTEGER DEFAULT 0,
    persisted_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
);

-- Source registry (trust scoring, health tracking)
CREATE TABLE IF NOT EXISTS source_registry (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    trust_score REAL DEFAULT 0.5,
    language TEXT DEFAULT 'hu',
    source_type TEXT DEFAULT 'web',
    total_fetches INTEGER DEFAULT 0,
    successful_extractions INTEGER DEFAULT 0,
    failed_fetches INTEGER DEFAULT 0,
    last_fetched_at TIMESTAMP,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    cooldown_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raw findings from web fetches
CREATE TABLE IF NOT EXISTS raw_findings (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    content TEXT,
    source_domain TEXT,
    search_query TEXT,
    connector_used TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
);

-- Extraction candidates (structured data from raw findings)
CREATE TABLE IF NOT EXISTS extraction_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    finding_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    extracted_data TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    status TEXT DEFAULT 'pending',
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id),
    FOREIGN KEY (finding_id) REFERENCES raw_findings(finding_id)
);

-- Persistence log (what happened to each candidate)
CREATE TABLE IF NOT EXISTS persistence_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    candidate_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_table TEXT,
    target_id TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id),
    FOREIGN KEY (candidate_id) REFERENCES extraction_candidates(candidate_id)
);

-- Review queue (low-confidence items awaiting manual review)
CREATE TABLE IF NOT EXISTS review_queue (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    candidate_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    confidence REAL,
    review_reason TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES research_runs(run_id),
    FOREIGN KEY (candidate_id) REFERENCES extraction_candidates(candidate_id)
);

-- Prompt effectiveness scoring
CREATE TABLE IF NOT EXISTS prompt_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_template_hash TEXT NOT NULL,
    prompt_type TEXT NOT NULL,
    total_uses INTEGER DEFAULT 0,
    successful_extractions INTEGER DEFAULT 0,
    avg_confidence REAL DEFAULT 0.0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Retry tracking
CREATE TABLE IF NOT EXISTS retry_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    attempt_count INTEGER DEFAULT 1,
    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_retry_at TIMESTAMP,
    resolved BOOLEAN DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_research_runs_status ON research_runs(status);
CREATE INDEX IF NOT EXISTS idx_research_events_run_id ON research_events(run_id);
CREATE INDEX IF NOT EXISTS idx_research_items_log_run_id ON research_items_log(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_findings_run_id ON raw_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_findings_url ON raw_findings(url);
CREATE INDEX IF NOT EXISTS idx_extraction_candidates_run_id ON extraction_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_candidates_status ON extraction_candidates(status);
CREATE INDEX IF NOT EXISTS idx_persistence_log_run_id ON persistence_log(run_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_retry_log_item_id ON retry_log(item_id);
CREATE INDEX IF NOT EXISTS idx_source_registry_domain ON source_registry(domain);

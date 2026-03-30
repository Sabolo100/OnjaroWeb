-- Autonomous Evolution System - Database Schema

CREATE TABLE IF NOT EXISTS project_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    claude_md_hash TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'INIT',
    phase TEXT NOT NULL DEFAULT 'INIT',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    feature_id TEXT,
    feature_title TEXT,
    error_message TEXT,
    cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    phase TEXT,
    agent_name TEXT,
    severity TEXT DEFAULT 'INFO',
    event_type TEXT,
    message TEXT,
    input_ref TEXT,
    output_ref TEXT,
    artifact_ref TEXT,
    git_ref TEXT,
    duration_ms INTEGER,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS feature_ideas (
    idea_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    rationale TEXT,
    estimated_size TEXT,
    testability_score REAL,
    affected_screen TEXT,
    rejected_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS feature_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    chosen_idea_id INTEGER,
    score REAL,
    rationale TEXT,
    alternatives_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (chosen_idea_id) REFERENCES feature_ideas(idea_id)
);

CREATE TABLE IF NOT EXISTS features_live (
    feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    files_changed TEXT,
    screen TEXT,
    committed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    commit_hash TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS screens_catalog (
    screen_id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT,
    name TEXT,
    description TEXT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_run TEXT,
    FOREIGN KEY (last_modified_run) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS tests (
    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    test_type TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    output_ref TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    size_bytes INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS git_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    message TEXT,
    files_changed TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS failures (
    failure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase TEXT,
    error_type TEXT,
    error_message TEXT,
    artifact_ref TEXT,
    recovery_action TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS recovery_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_id INTEGER NOT NULL,
    action_type TEXT,
    result TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (failure_id) REFERENCES failures(failure_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_feature_ideas_run_id ON feature_ideas(run_id);
CREATE INDEX IF NOT EXISTS idx_features_live_run_id ON features_live(run_id);
CREATE INDEX IF NOT EXISTS idx_tests_run_id ON tests(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_failures_run_id ON failures(run_id);
CREATE INDEX IF NOT EXISTS idx_git_history_run_id ON git_history(run_id);

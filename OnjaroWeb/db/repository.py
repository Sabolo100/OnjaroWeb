"""Data access layer for all database operations."""

import json
from datetime import datetime, date

from db.connection import get_connection, transaction


class Repository:
    """Central repository for all database operations."""

    # --- Runs ---

    def create_run(self, run_id: str) -> None:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, status, phase, started_at) VALUES (?, 'INIT', 'INIT', ?)",
                (run_id, datetime.now().isoformat()),
            )

    def update_run_phase(self, run_id: str, phase: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET phase = ? WHERE run_id = ?",
            (phase, run_id),
        )
        conn.commit()

    def update_run_status(self, run_id: str, status: str, error_message: str = None) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET status = ?, ended_at = ?, error_message = ? WHERE run_id = ?",
            (status, datetime.now().isoformat(), error_message, run_id),
        )
        conn.commit()

    def update_run_cost(self, run_id: str, cost_usd: float) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET cost_usd = cost_usd + ? WHERE run_id = ?",
            (cost_usd, run_id),
        )
        conn.commit()

    def update_run_feature(self, run_id: str, feature_title: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET feature_title = ? WHERE run_id = ?",
            (feature_title, run_id),
        )
        conn.commit()

    def complete_run(self, run_id: str, duration_ms: int) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE runs SET status = 'COMPLETE', ended_at = ?, duration_ms = ? WHERE run_id = ?",
            (datetime.now().isoformat(), duration_ms, run_id),
        )
        conn.commit()

    def get_run(self, run_id: str) -> dict:
        conn = get_connection()
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_recent_runs(self, limit: int = 20) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_run(self) -> dict:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM runs WHERE status IN ('INIT', 'RUNNING') ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_daily_cost(self) -> float:
        conn = get_connection()
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM runs WHERE started_at >= ?",
            (today,),
        ).fetchone()
        return row["total"]

    # --- Events ---

    def log_event(self, run_id: str, phase: str, agent_name: str, severity: str,
                  event_type: str, message: str, input_ref: str = None,
                  output_ref: str = None, artifact_ref: str = None,
                  git_ref: str = None, duration_ms: int = None) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO run_events
               (run_id, phase, agent_name, severity, event_type, message,
                input_ref, output_ref, artifact_ref, git_ref, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, phase, agent_name, severity, event_type, message,
             input_ref, output_ref, artifact_ref, git_ref, duration_ms),
        )
        conn.commit()
        return cursor.lastrowid

    def get_run_events(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY timestamp ASC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Feature Ideas ---

    def save_idea(self, run_id: str, idea: dict) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO feature_ideas
               (run_id, title, description, rationale, estimated_size,
                testability_score, affected_screen)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, idea.get("title"), idea.get("description"),
             idea.get("rationale"), idea.get("estimated_size"),
             idea.get("testability_score"), idea.get("affected_screen")),
        )
        conn.commit()
        return cursor.lastrowid

    def get_ideas_for_run(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM feature_ideas WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_ideas(self, limit: int = 50) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM feature_ideas ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def reject_idea(self, idea_id: int, reason: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE feature_ideas SET rejected_reason = ? WHERE idea_id = ?",
            (reason, idea_id),
        )
        conn.commit()

    # --- Feature Decisions ---

    def save_decision(self, run_id: str, chosen_idea_id: int, score: float,
                      rationale: str, alternatives_json: str) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO feature_decisions
               (run_id, chosen_idea_id, score, rationale, alternatives_json)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, chosen_idea_id, score, rationale, alternatives_json),
        )
        conn.commit()
        return cursor.lastrowid

    # --- Live Features ---

    def mark_feature_live(self, run_id: str, title: str, description: str,
                          files_changed: str, screen: str, commit_hash: str) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO features_live
               (run_id, title, description, files_changed, screen, commit_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, title, description, files_changed, screen, commit_hash),
        )
        conn.commit()
        return cursor.lastrowid

    def get_live_features(self, limit: int = 100) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM features_live ORDER BY committed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Screens ---

    def upsert_screen(self, route: str, name: str, description: str, run_id: str = None) -> None:
        conn = get_connection()
        existing = conn.execute(
            "SELECT screen_id FROM screens_catalog WHERE route = ?", (route,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE screens_catalog SET name=?, description=?, last_modified_run=? WHERE route=?",
                (name, description, run_id, route),
            )
        else:
            conn.execute(
                "INSERT INTO screens_catalog (route, name, description, last_modified_run) VALUES (?, ?, ?, ?)",
                (route, name, description, run_id),
            )
        conn.commit()

    def get_screens(self) -> list:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM screens_catalog ORDER BY route").fetchall()
        return [dict(r) for r in rows]

    # --- Tests ---

    def save_test(self, run_id: str, test_type: str, passed: bool,
                  output_ref: str = None, duration_ms: int = None) -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO tests (run_id, test_type, passed, output_ref, duration_ms) VALUES (?, ?, ?, ?, ?)",
            (run_id, test_type, int(passed), output_ref, duration_ms),
        )
        conn.commit()
        return cursor.lastrowid

    def get_tests_for_run(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM tests WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Artifacts ---

    def save_artifact(self, run_id: str, artifact_type: str, path: str,
                      size_bytes: int = 0) -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO artifacts (run_id, type, path, size_bytes) VALUES (?, ?, ?, ?)",
            (run_id, artifact_type, path, size_bytes),
        )
        conn.commit()
        return cursor.lastrowid

    def get_artifacts_for_run(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Git History ---

    def save_git_history(self, run_id: str, commit_hash: str, message: str,
                         files_changed: str) -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO git_history (run_id, commit_hash, message, files_changed) VALUES (?, ?, ?, ?)",
            (run_id, commit_hash, message, files_changed),
        )
        conn.commit()
        return cursor.lastrowid

    # --- Failures ---

    def save_failure(self, run_id: str, phase: str, error_type: str,
                     error_message: str, artifact_ref: str = None,
                     recovery_action: str = None) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO failures
               (run_id, phase, error_type, error_message, artifact_ref, recovery_action)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, phase, error_type, error_message, artifact_ref, recovery_action),
        )
        conn.commit()
        return cursor.lastrowid

    def save_recovery_action(self, failure_id: int, action_type: str, result: str) -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO recovery_actions (failure_id, action_type, result) VALUES (?, ?, ?)",
            (failure_id, action_type, result),
        )
        conn.commit()
        return cursor.lastrowid

    def get_recent_failures(self, limit: int = 10) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM failures ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

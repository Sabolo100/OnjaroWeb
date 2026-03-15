"""Repository for research module database operations."""

import json
import logging
from datetime import datetime, timezone

from db.connection import get_connection, transaction

logger = logging.getLogger("onjaro.research.repo")


class ResearchRepository:
    """Data access layer for research orchestration tables."""

    # ── Research Runs ──

    def create_research_run(self, run_id: str, project: str = "onjaro",
                            trigger_type: str = "scheduled") -> dict:
        with transaction() as conn:
            conn.execute(
                """INSERT INTO research_runs (run_id, status, phase, project, trigger_type)
                   VALUES (?, 'RUNNING', 'QUEUED', ?, ?)""",
                (run_id, project, trigger_type),
            )
        return {"run_id": run_id, "status": "RUNNING", "project": project}

    def update_research_phase(self, run_id: str, phase: str) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE research_runs SET phase = ? WHERE run_id = ?",
                (phase, run_id),
            )

    def update_research_status(self, run_id: str, status: str,
                               error_message: str = None) -> None:
        with transaction() as conn:
            conn.execute(
                """UPDATE research_runs
                   SET status = ?, error_message = ?, ended_at = CURRENT_TIMESTAMP
                   WHERE run_id = ?""",
                (status, error_message, run_id),
            )

    def update_research_items_count(self, run_id: str, total: int = None,
                                    completed: int = None, failed: int = None) -> None:
        parts = []
        params = []
        if total is not None:
            parts.append("items_total = ?")
            params.append(total)
        if completed is not None:
            parts.append("items_completed = ?")
            params.append(completed)
        if failed is not None:
            parts.append("items_failed = ?")
            params.append(failed)
        if not parts:
            return
        params.append(run_id)
        with transaction() as conn:
            conn.execute(
                f"UPDATE research_runs SET {', '.join(parts)} WHERE run_id = ?",
                params,
            )

    def update_research_cost(self, run_id: str, cost_usd: float) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE research_runs SET cost_usd = cost_usd + ? WHERE run_id = ?",
                (cost_usd, run_id),
            )

    def complete_research_run(self, run_id: str, status: str = "COMPLETED",
                              duration_ms: int = 0) -> None:
        with transaction() as conn:
            conn.execute(
                """UPDATE research_runs
                   SET status = ?, ended_at = CURRENT_TIMESTAMP, duration_ms = ?
                   WHERE run_id = ?""",
                (status, duration_ms, run_id),
            )

    def get_research_run(self, run_id: str) -> dict:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM research_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_research_runs(self, limit: int = 50) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM research_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_research_run(self) -> dict:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM research_runs WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    # ── Research Events ──

    def log_research_event(self, run_id: str, phase: str = "", agent_name: str = "",
                           severity: str = "INFO", event_type: str = "",
                           message: str = "", data: dict = None,
                           duration_ms: int = None) -> None:
        data_json = json.dumps(data, default=str, ensure_ascii=False) if data else None
        with transaction() as conn:
            conn.execute(
                """INSERT INTO research_events
                   (run_id, phase, agent_name, severity, event_type, message, data_json, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, phase, agent_name, severity, event_type, message, data_json, duration_ms),
            )

    def get_research_events(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM research_events WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Research Items Log ──

    def create_research_item_log(self, run_id: str, item_id: str) -> None:
        with transaction() as conn:
            conn.execute(
                """INSERT INTO research_items_log (run_id, item_id, status, started_at)
                   VALUES (?, ?, 'running', CURRENT_TIMESTAMP)""",
                (run_id, item_id),
            )

    def update_research_item_log(self, run_id: str, item_id: str,
                                 status: str = None, phase: str = None,
                                 raw_findings_count: int = None,
                                 extracted_count: int = None,
                                 validated_count: int = None,
                                 persisted_count: int = None,
                                 skipped_count: int = None,
                                 error_message: str = None) -> None:
        parts = []
        params = []
        for field, val in [("status", status), ("phase", phase),
                           ("raw_findings_count", raw_findings_count),
                           ("extracted_count", extracted_count),
                           ("validated_count", validated_count),
                           ("persisted_count", persisted_count),
                           ("skipped_count", skipped_count),
                           ("error_message", error_message)]:
            if val is not None:
                parts.append(f"{field} = ?")
                params.append(val)
        if status in ("completed", "failed"):
            parts.append("completed_at = CURRENT_TIMESTAMP")
        if not parts:
            return
        params.extend([run_id, item_id])
        with transaction() as conn:
            conn.execute(
                f"UPDATE research_items_log SET {', '.join(parts)} WHERE run_id = ? AND item_id = ?",
                params,
            )

    def get_research_items_for_run(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM research_items_log WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Raw Findings ──

    def save_raw_finding(self, run_id: str, item_id: str, url: str,
                         title: str = None, snippet: str = None,
                         content: str = None, source_domain: str = None,
                         search_query: str = None, connector_used: str = None) -> int:
        with transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO raw_findings
                   (run_id, item_id, url, title, snippet, content, source_domain, search_query, connector_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, item_id, url, title, snippet, content, source_domain, search_query, connector_used),
            )
            return cursor.lastrowid

    def get_raw_findings_for_run(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM raw_findings WHERE run_id = ? ORDER BY finding_id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_raw_findings_for_item(self, run_id: str, item_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM raw_findings WHERE run_id = ? AND item_id = ? ORDER BY finding_id",
            (run_id, item_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Extraction Candidates ──

    def save_extraction_candidate(self, run_id: str, finding_id: int, item_id: str,
                                  extracted_data: dict, confidence: float = 0.0,
                                  status: str = "pending") -> int:
        data_json = json.dumps(extracted_data, default=str, ensure_ascii=False)
        with transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO extraction_candidates
                   (run_id, finding_id, item_id, extracted_data, confidence, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, finding_id, item_id, data_json, confidence, status),
            )
            return cursor.lastrowid

    def update_candidate_status(self, candidate_id: int, status: str,
                                rejection_reason: str = None) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE extraction_candidates SET status = ?, rejection_reason = ? WHERE candidate_id = ?",
                (status, rejection_reason, candidate_id),
            )

    def get_candidates_for_run(self, run_id: str, status: str = None) -> list:
        conn = get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM extraction_candidates WHERE run_id = ? AND status = ?",
                (run_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM extraction_candidates WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Persistence Log ──

    def save_persistence_result(self, run_id: str, candidate_id: int,
                                action: str, target_table: str = None,
                                target_id: str = None, reason: str = None) -> None:
        with transaction() as conn:
            conn.execute(
                """INSERT INTO persistence_log
                   (run_id, candidate_id, action, target_table, target_id, reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, candidate_id, action, target_table, target_id, reason),
            )

    def get_persistence_results(self, run_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM persistence_log WHERE run_id = ? ORDER BY log_id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Source Registry ──

    def upsert_source(self, domain: str, trust_score: float = 0.5,
                      language: str = "hu", source_type: str = "web") -> None:
        with transaction() as conn:
            conn.execute(
                """INSERT INTO source_registry (domain, trust_score, language, source_type)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                       trust_score = excluded.trust_score,
                       language = excluded.language""",
                (domain, trust_score, language, source_type),
            )

    def update_source_fetch(self, domain: str, success: bool) -> None:
        with transaction() as conn:
            if success:
                conn.execute(
                    """UPDATE source_registry
                       SET total_fetches = total_fetches + 1,
                           successful_extractions = successful_extractions + 1,
                           last_fetched_at = CURRENT_TIMESTAMP,
                           last_success_at = CURRENT_TIMESTAMP
                       WHERE domain = ?""",
                    (domain,),
                )
            else:
                conn.execute(
                    """UPDATE source_registry
                       SET total_fetches = total_fetches + 1,
                           failed_fetches = failed_fetches + 1,
                           last_fetched_at = CURRENT_TIMESTAMP,
                           last_failure_at = CURRENT_TIMESTAMP
                       WHERE domain = ?""",
                    (domain,),
                )

    def get_sources(self, min_trust: float = 0.0) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM source_registry WHERE trust_score >= ? ORDER BY trust_score DESC",
            (min_trust,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_source_trust_score(self, domain: str, new_score: float) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE source_registry SET trust_score = ? WHERE domain = ?",
                (new_score, domain),
            )

    # ── Review Queue ──

    def add_to_review(self, run_id: str, candidate_id: int,
                      confidence: float, review_reason: str) -> int:
        with transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO review_queue
                   (run_id, candidate_id, confidence, review_reason)
                   VALUES (?, ?, ?, ?)""",
                (run_id, candidate_id, confidence, review_reason),
            )
            return cursor.lastrowid

    def get_pending_reviews(self) -> list:
        conn = get_connection()
        rows = conn.execute(
            """SELECT rq.*, ec.extracted_data, ec.item_id
               FROM review_queue rq
               JOIN extraction_candidates ec ON rq.candidate_id = ec.candidate_id
               WHERE rq.status = 'pending'
               ORDER BY rq.created_at""",
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_review(self, review_id: int, status: str,
                       reviewer: str = "manual", review_notes: str = None) -> None:
        with transaction() as conn:
            conn.execute(
                """UPDATE review_queue
                   SET status = ?, reviewer = ?, reviewed_at = CURRENT_TIMESTAMP, review_notes = ?
                   WHERE review_id = ?""",
                (status, reviewer, review_notes, review_id),
            )

    # ── Prompt Scores ──

    def update_prompt_score(self, prompt_hash: str, prompt_type: str,
                            successful: bool, confidence: float = 0.0) -> None:
        with transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM prompt_scores WHERE prompt_template_hash = ?",
                (prompt_hash,),
            ).fetchone()
            if existing:
                new_total = existing["total_uses"] + 1
                new_success = existing["successful_extractions"] + (1 if successful else 0)
                new_avg = ((existing["avg_confidence"] * existing["total_uses"]) + confidence) / new_total
                conn.execute(
                    """UPDATE prompt_scores
                       SET total_uses = ?, successful_extractions = ?,
                           avg_confidence = ?, last_used_at = CURRENT_TIMESTAMP
                       WHERE prompt_template_hash = ?""",
                    (new_total, new_success, new_avg, prompt_hash),
                )
            else:
                conn.execute(
                    """INSERT INTO prompt_scores
                       (prompt_template_hash, prompt_type, total_uses,
                        successful_extractions, avg_confidence, last_used_at)
                       VALUES (?, ?, 1, ?, ?, CURRENT_TIMESTAMP)""",
                    (prompt_hash, prompt_type, 1 if successful else 0, confidence),
                )

    # ── Retry Log ──

    def record_retry(self, item_id: str, error_type: str,
                     error_message: str = None, next_retry_at: str = None) -> None:
        with transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM retry_log WHERE item_id = ? AND resolved = 0",
                (item_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE retry_log
                       SET attempt_count = attempt_count + 1,
                           last_attempt_at = CURRENT_TIMESTAMP,
                           next_retry_at = ?, error_message = ?
                       WHERE id = ?""",
                    (next_retry_at, error_message, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO retry_log (item_id, error_type, error_message, next_retry_at)
                       VALUES (?, ?, ?, ?)""",
                    (item_id, error_type, error_message, next_retry_at),
                )

    def resolve_retry(self, item_id: str) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE retry_log SET resolved = 1 WHERE item_id = ? AND resolved = 0",
                (item_id,),
            )

    def get_daily_research_cost(self) -> float:
        conn = get_connection()
        row = conn.execute(
            """SELECT COALESCE(SUM(cost_usd), 0) as total
               FROM research_runs
               WHERE date(started_at) = date('now')"""
        ).fetchone()
        return row["total"] if row else 0.0

"""Activity Dashboard - Flask + Socket.IO real-time monitoring."""

from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from orchestrator.config import RUN_INTERVAL_MINUTES, EVOLUTION_ENABLED, RESEARCH_ENABLED
from orchestrator.event_bus import EventBus
from db.repository import Repository
from db.research_repository import ResearchRepository

# Shared state: next scheduled run time (set by main.py)
next_run_at = None
session_started_at = datetime.now(timezone.utc)


def set_next_run_at(dt: datetime):
    global next_run_at
    next_run_at = dt


def _force_persist_candidate(review_id: int,
                              research_repo: ResearchRepository) -> bool:
    """Persist a review-queue candidate as a new entity.

    Called when a user rejects a duplicate suggestion, meaning the candidate
    is genuinely a *different* entity and should be saved to Supabase.

    Returns True if persisted successfully, False otherwise.
    """
    import json
    import sqlite3
    from db.connection import get_connection
    from research.config_loader import ProjectConfig
    from research.pipeline.persister import ResearchPersister
    from research.models import ExtractionCandidate

    conn = get_connection()
    row = conn.execute(
        """SELECT rq.candidate_id, rq.run_id,
                  ec.extracted_data, ec.confidence, ec.item_id, ec.finding_id
           FROM review_queue rq
           JOIN extraction_candidates ec ON rq.candidate_id = ec.candidate_id
           WHERE rq.review_id = ?""",
        (review_id,),
    ).fetchone()

    if not row:
        return False

    candidate_id = row["candidate_id"]
    run_id = row["run_id"]
    item_id = row["item_id"]
    extracted_data = json.loads(row["extracted_data"]) if row["extracted_data"] else {}
    confidence = row["confidence"] or 0.5

    # Load the item config to know target_table etc.
    config = ProjectConfig()
    items = config.load_items()
    item = next((i for i in items if i.get("id") == item_id), None)
    if not item:
        # Fallback: infer target_table from item_id naming convention
        if "people" in item_id or "person" in item_id:
            target_table = "people"
        elif "building" in item_id:
            target_table = "buildings"
        elif "company" in item_id or "enrich" in item_id:
            target_table = "companies"
        else:
            target_table = "companies"
        item = {"id": item_id, "target_table": target_table,
                "schema_name": target_table.rstrip("s"),
                "min_confidence": 0.4, "auto_approve_above": 0.9}

    # Remove the duplicate-marker so the persister inserts fresh
    extracted_data.pop("_update_existing_id", None)

    candidate = ExtractionCandidate(
        candidate_id=candidate_id,
        finding_id=row["finding_id"],
        item_id=item_id,
        extracted_data=extracted_data,
        confidence=confidence,
        status="validated",
    )

    persister = ResearchPersister(research_repo, config)
    count = persister.persist(run_id, item, [candidate])
    return count > 0


def create_app(event_bus: EventBus = None, repo: Repository = None,
               research_repo: ResearchRepository = None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "onjaro-evolution-dashboard"
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    repo_instance = repo if repo else Repository()
    research_repo_instance = research_repo if research_repo else ResearchRepository()

    # ── Pages ──

    @app.route("/")
    def index():
        return render_template("index.html")

    # ── Evolution API ──

    @app.route("/api/status")
    def api_status():
        now = datetime.now(timezone.utc)
        next_run_iso = next_run_at.isoformat() if next_run_at else None
        return jsonify({
            "now": now.isoformat(),
            "next_run_at": next_run_iso,
            "interval_minutes": RUN_INTERVAL_MINUTES,
            "evolution_enabled": EVOLUTION_ENABLED,
            "research_enabled": RESEARCH_ENABLED,
            "session_started_at": session_started_at.isoformat(),
        })

    @app.route("/api/runs")
    def api_runs():
        return jsonify(repo_instance.get_recent_runs(limit=50))

    @app.route("/api/runs/<run_id>")
    def api_run_detail(run_id):
        run = repo_instance.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
        return jsonify({
            "run": run,
            "events": repo_instance.get_run_events(run_id),
            "tests": repo_instance.get_tests_for_run(run_id),
            "ideas": repo_instance.get_ideas_for_run(run_id),
            "artifacts": repo_instance.get_artifacts_for_run(run_id),
        })

    @app.route("/api/runs/<run_id>/ideas")
    def api_run_ideas(run_id):
        return jsonify(repo_instance.get_ideas_for_run(run_id))

    @app.route("/api/ideas/recent")
    def api_recent_ideas():
        return jsonify(repo_instance.get_recent_ideas(limit=30))

    @app.route("/api/features")
    def api_features():
        return jsonify(repo_instance.get_live_features(limit=100))

    @app.route("/api/failures")
    def api_failures():
        return jsonify(repo_instance.get_recent_failures(limit=20))

    @app.route("/api/screens")
    def api_screens():
        return jsonify(repo_instance.get_screens())

    # ── Research API ──

    @app.route("/api/research/status")
    def api_research_status():
        active = research_repo_instance.get_active_research_run()
        pending_reviews = len(research_repo_instance.get_pending_reviews())
        return jsonify({
            "active_run": active,
            "pending_reviews": pending_reviews,
        })

    @app.route("/api/research/runs")
    def api_research_runs():
        return jsonify(research_repo_instance.get_recent_research_runs(limit=50))

    @app.route("/api/research/runs/<run_id>")
    def api_research_run_detail(run_id):
        run = research_repo_instance.get_research_run(run_id)
        if not run:
            return jsonify({"error": "Research run not found"}), 404
        return jsonify({
            "run": run,
            "events": research_repo_instance.get_research_events(run_id),
            "items": research_repo_instance.get_research_items_for_run(run_id),
            "raw_findings": research_repo_instance.get_raw_findings_for_run(run_id),
            "candidates": research_repo_instance.get_candidates_for_run(run_id),
            "persistence": research_repo_instance.get_persistence_results(run_id),
        })

    @app.route("/api/research/sources")
    def api_research_sources():
        return jsonify(research_repo_instance.get_sources())

    @app.route("/api/research/reviews")
    def api_research_reviews():
        return jsonify(research_repo_instance.get_pending_reviews())

    @app.route("/api/research/reviews/<int:review_id>/approve", methods=["POST"])
    def api_approve_review(review_id):
        notes = request.json.get("notes", "") if request.is_json else ""
        research_repo_instance.resolve_review(review_id, "approved",
                                              reviewer="manual", review_notes=notes)
        return jsonify({"status": "approved", "review_id": review_id})

    @app.route("/api/research/reviews/<int:review_id>/reject", methods=["POST"])
    def api_reject_review(review_id):
        """Reject a duplicate suggestion — these are NOT the same entity.

        After marking the review as rejected, we persist the candidate as a
        brand-new record, since the user confirmed it is distinct from the
        existing one.
        """
        notes = request.json.get("notes", "") if request.is_json else ""
        research_repo_instance.resolve_review(review_id, "rejected",
                                              reviewer="manual", review_notes=notes)

        # Force-persist the candidate as a new (separate) entity
        try:
            persisted = _force_persist_candidate(review_id, research_repo_instance)
            return jsonify({"status": "rejected", "review_id": review_id,
                            "created_new": persisted})
        except Exception as e:
            import logging
            logging.getLogger("onjaro.dashboard").warning(
                "Force-persist after rejection failed for review %d: %s", review_id, e
            )
            return jsonify({"status": "rejected", "review_id": review_id,
                            "created_new": False, "error": str(e)})

    # ── Socket.IO ──

    @socketio.on("connect")
    def handle_connect():
        # Send active evolution run
        active_run = repo_instance.get_active_run()
        if active_run:
            socketio.emit("active_run", active_run)

        # Send active research run
        active_research = research_repo_instance.get_active_research_run()
        if active_research:
            socketio.emit("active_research_run", active_research)
            # Also send timeline events for the active run so the dashboard
            # is populated immediately (fix #4: timeline empty on load)
            run_id = active_research.get("run_id")
            if run_id:
                events = research_repo_instance.get_research_events(run_id)
                if events:
                    socketio.emit("research_timeline_history", events)
        else:
            # No active run — send events from the most recent completed run
            recent_runs = research_repo_instance.get_recent_research_runs(limit=1)
            if recent_runs:
                last_run_id = recent_runs[0].get("run_id")
                if last_run_id:
                    events = research_repo_instance.get_research_events(last_run_id)
                    if events:
                        socketio.emit("research_timeline_history", events)

    return app, socketio

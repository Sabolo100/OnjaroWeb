"""Activity Dashboard - Flask + Socket.IO real-time monitoring."""

from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from orchestrator.config import RUN_INTERVAL_MINUTES
from orchestrator.event_bus import EventBus
from db.repository import Repository
from db.research_repository import ResearchRepository

# Shared state: next scheduled run time (set by main.py)
next_run_at = None


def set_next_run_at(dt: datetime):
    global next_run_at
    next_run_at = dt


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
        notes = request.json.get("notes", "") if request.is_json else ""
        research_repo_instance.resolve_review(review_id, "rejected",
                                              reviewer="manual", review_notes=notes)
        return jsonify({"status": "rejected", "review_id": review_id})

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

    return app, socketio

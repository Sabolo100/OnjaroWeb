"""Main entry point for the Autonomous Evolution System."""

import logging
import os
import sys
import time
import signal
import threading
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from orchestrator.config import (
    RUN_INTERVAL_MINUTES,
    LOGS_DIR,
    DASHBOARD_PORT,
    DASHBOARD_HOST,
    PROJECT_ROOT,
)
from orchestrator.lock import Lock
from orchestrator.event_bus import EventBus
from orchestrator.claude_executor import ClaudeExecutor
from orchestrator.git_manager import GitManager
from orchestrator.run_manager import RunManager
from db.connection import init_db
from db.repository import Repository

# Setup logging
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOGS_DIR, "orchestrator.log")),
    ],
)
logger = logging.getLogger("onjaro.main")


# Global components
event_bus = EventBus()
repo = Repository()
executor = ClaudeExecutor()
git_manager = GitManager()
run_manager = RunManager(executor, repo, event_bus, git_manager)
dashboard_socketio = None


def db_event_logger(event: dict):
    """Subscribe to event bus and log events to database."""
    try:
        repo.log_event(
            run_id=event.get("run_id", "system"),
            phase=event.get("phase", ""),
            agent_name=event.get("agent_name", ""),
            severity=event.get("severity", "INFO"),
            event_type=event.get("event_type", ""),
            message=event.get("message", ""),
        )
    except Exception as e:
        logger.error("Failed to log event to DB: %s", e)


def dashboard_event_emitter(event: dict):
    """Subscribe to event bus and push events to dashboard via Socket.IO."""
    global dashboard_socketio
    if dashboard_socketio:
        try:
            dashboard_socketio.emit(
                event.get("event_type", "event"),
                event,
                namespace="/",
            )
        except Exception as e:
            logger.error("Failed to emit dashboard event: %s", e)


def update_next_run_time():
    """Update the dashboard with the next scheduled run time."""
    try:
        from dashboard.app import set_next_run_at
        next_run = datetime.now(timezone.utc) + timedelta(minutes=RUN_INTERVAL_MINUTES)
        set_next_run_at(next_run)
        if dashboard_socketio:
            dashboard_socketio.emit("next_run_scheduled", {
                "next_run_at": next_run.isoformat(),
                "interval_minutes": RUN_INTERVAL_MINUTES,
            })
    except Exception:
        pass


def run_cycle():
    """Execute a single evolution cycle with lock protection."""
    lock = Lock()
    if not lock.acquire():
        logger.warning("Another run is in progress, skipping this cycle.")
        return

    try:
        logger.info("=" * 60)
        logger.info("Starting evolution cycle")
        logger.info("=" * 60)

        run_id = run_manager.execute_run()
        if run_id:
            run = repo.get_run(run_id)
            status = run.get("status", "UNKNOWN") if run else "UNKNOWN"
            logger.info("Cycle completed. Run: %s, Status: %s", run_id, status)
        else:
            logger.info("Cycle skipped (budget cap or other reason)")

    except Exception as e:
        logger.error("Cycle failed with unexpected error: %s", e)
    finally:
        lock.release()
        update_next_run_time()


def start_dashboard():
    """Start the activity dashboard in a background thread."""
    global dashboard_socketio
    try:
        from dashboard.app import create_app, set_next_run_at
        app, socketio = create_app(event_bus, repo)
        dashboard_socketio = socketio
        event_bus.subscribe(dashboard_event_emitter)

        logger.info("Starting dashboard on %s:%d", DASHBOARD_HOST, DASHBOARD_PORT)
        socketio.run(
            app,
            host=DASHBOARD_HOST,
            port=DASHBOARD_PORT,
            allow_unsafe_werkzeug=True,
            use_reloader=False,
        )
    except ImportError as e:
        logger.warning("Dashboard dependencies not available: %s", e)
    except Exception as e:
        logger.error("Dashboard failed to start: %s", e)


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Autonomous Evolution System starting")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Run interval: %d minutes", RUN_INTERVAL_MINUTES)
    logger.info("=" * 60)

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Subscribe event bus to DB logger
    event_bus.subscribe(db_event_logger)

    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard thread started")

    # Setup scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_cycle,
        "interval",
        minutes=RUN_INTERVAL_MINUTES,
        max_instances=1,
        id="evolution_cycle",
    )
    scheduler.start()
    logger.info("Scheduler started (every %d minutes)", RUN_INTERVAL_MINUTES)

    # Run immediately on start
    logger.info("Running initial cycle...")
    run_cycle()

    # Handle graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()

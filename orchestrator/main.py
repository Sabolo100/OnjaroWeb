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
    EVOLUTION_ENABLED,
    RESEARCH_ENABLED,
    RUN_ON_STARTUP,
)
from orchestrator.lock import Lock
from orchestrator.event_bus import EventBus
from orchestrator.claude_executor import ClaudeExecutor
from orchestrator.git_manager import GitManager
from orchestrator.run_manager import RunManager
from db.connection import init_db
from db.repository import Repository
from db.research_repository import ResearchRepository
from research.run_manager import ResearchRunManager
from research.lock import ResearchLock
from research.config import RESEARCH_RUN_INTERVAL_MINUTES

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

# Research components
research_repo = ResearchRepository()
research_manager = ResearchRunManager(research_repo, event_bus)


def _init_research_pipeline():
    """Initialize research pipeline components and wire them to the run manager."""
    try:
        from research.config_loader import ProjectConfig
        from research.pipeline.fetcher import ResearchFetcher
        from research.pipeline.extractor import ResearchExtractor
        from research.pipeline.validator import ResearchValidator
        from research.pipeline.normalizer import ContentNormalizer
        from research.pipeline.deduplicator import ResearchDeduplicator
        from research.pipeline.persister import ResearchPersister

        config = ProjectConfig()
        if not config.is_configured():
            logger.warning("Research config not found at %s, research will be inactive",
                           config.config_dir)
            return

        research_manager.set_config_loader(config)
        research_manager.set_pipeline_components(
            fetcher=ResearchFetcher(research_repo, config),
            extractor=ResearchExtractor(research_repo, config),
            validator=ResearchValidator(research_repo, config),
            normalizer=ContentNormalizer(config),
            deduplicator=ResearchDeduplicator(research_repo, config),
            persister=ResearchPersister(research_repo, config),
        )

        # Register seed sources
        sources = config.load_sources()
        for source in sources:
            research_repo.upsert_source(
                domain=source.url,
                trust_score=source.trust_score,
                language=source.language,
                source_type=source.source_type,
            )

        logger.info("Research pipeline initialized with %d seed sources", len(sources))

    except Exception as e:
        logger.error("Failed to initialize research pipeline: %s", e)


def db_event_logger(event: dict):
    """Subscribe to event bus and log events to database."""
    # Research events have their own repository — skip them here to avoid FK errors
    if event.get("run_id", "").startswith("res_"):
        return
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


def research_cycle():
    """Execute a single research cycle with lock protection."""
    lock = ResearchLock()
    if not lock.acquire():
        logger.warning("Another research run is in progress, skipping.")
        return

    try:
        logger.info("=" * 60)
        logger.info("Starting research cycle")
        logger.info("=" * 60)

        run_id = research_manager.execute_research_run()
        if run_id:
            run = research_repo.get_research_run(run_id)
            status = run.get("status", "UNKNOWN") if run else "UNKNOWN"
            logger.info("Research cycle completed. Run: %s, Status: %s", run_id, status)
        else:
            logger.info("Research cycle skipped (budget cap or other reason)")

    except Exception as e:
        logger.error("Research cycle failed: %s", e)
    finally:
        lock.release()


def start_dashboard():
    """Start the activity dashboard in a background thread."""
    global dashboard_socketio
    try:
        from dashboard.app import create_app, set_next_run_at
        app, socketio = create_app(event_bus, repo, research_repo)
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


def _wait_for_launch_config():
    """Wait for the launcher page to submit config via /api/launch.

    Returns the launch config dict, or None if not using the launcher.
    """
    from dashboard.app import get_launch_config
    import time as _time

    logger.info("Launcher page active at http://localhost:%d — waiting for RUN...",
                DASHBOARD_PORT)

    while True:
        cfg = get_launch_config()
        if cfg is not None:
            return cfg
        _time.sleep(0.5)


def _apply_research_item_config(item_config):
    """Temporarily patch items.yaml 'enabled' flags based on launcher selection.

    This modifies the in-memory config_loader so that disabled items are
    skipped by the research run manager.
    """
    if not item_config:
        return

    try:
        from research.config_loader import ProjectConfig
        config = ProjectConfig()
        items = config.load_items()
        for item in items:
            item_id = item.get("id", "")
            if item_id in item_config:
                item["enabled"] = item_config[item_id]
        logger.info("Research items configured: %s",
                    {i["id"]: i.get("enabled", True) for i in items})
    except Exception as e:
        logger.warning("Failed to apply research item config: %s", e)


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("FM Intel - Piaci Intelligencia Platform")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("=" * 60)

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Clean up any stale runs from previous crashed/interrupted sessions
    stale = repo.cancel_stale_runs()
    if stale:
        logger.info("Cancelled %d stale evolution run(s) from previous session", stale)

    # Clean up stale research runs (e.g. after crash or DST clock jump)
    stale_research = research_repo.cancel_stale_research_runs()
    if stale_research:
        logger.info("Cancelled %d stale research run(s) from previous session", stale_research)

    # Subscribe event bus to DB logger
    event_bus.subscribe(db_event_logger)

    # Start dashboard in background thread (serves launcher page first)
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard thread started — launcher at http://localhost:%d", DASHBOARD_PORT)

    # Wait for launcher config (or use .env defaults if RUN_ON_STARTUP=1)
    evo_enabled = EVOLUTION_ENABLED
    res_enabled = RESEARCH_ENABLED

    if RUN_ON_STARTUP:
        # Legacy mode: skip launcher, use .env settings directly
        logger.info("RUN_ON_STARTUP=1 — skipping launcher, using .env config")
        logger.info("Evolution: %s, Research: %s", "ON" if evo_enabled else "OFF",
                    "ON" if res_enabled else "OFF")
    else:
        # New flow: wait for launcher page to submit config
        cfg = _wait_for_launch_config()
        logger.info("Launch config received from launcher UI")

        evo_enabled = cfg.get("evolution_enabled", False)
        # Research is enabled if any research item is turned on
        research_items = cfg.get("research_items", {})
        res_enabled = any(research_items.values())

        # Apply per-item enabled/disabled flags
        if res_enabled:
            _apply_research_item_config(research_items)

        logger.info("Evolution: %s, Research: %s (items: %s)",
                    "ON" if evo_enabled else "OFF",
                    "ON" if res_enabled else "OFF",
                    research_items)

    # Initialize research pipeline
    if res_enabled:
        _init_research_pipeline()

    # Setup scheduler — use UTC timezone to avoid DST clock-jump missed runs
    scheduler = BackgroundScheduler(timezone="UTC")
    if evo_enabled:
        scheduler.add_job(
            run_cycle,
            "interval",
            minutes=RUN_INTERVAL_MINUTES,
            max_instances=1,
            id="evolution_cycle",
        )
        logger.info("Evolution scheduler: every %d min", RUN_INTERVAL_MINUTES)
    if res_enabled:
        scheduler.add_job(
            research_cycle,
            "interval",
            minutes=RESEARCH_RUN_INTERVAL_MINUTES,
            max_instances=1,
            id="research_cycle",
        )
        logger.info("Research scheduler: every %d min", RESEARCH_RUN_INTERVAL_MINUTES)
    scheduler.start()

    # Run first cycle immediately
    if evo_enabled:
        logger.info("Running initial evolution cycle...")
        run_cycle()
    if res_enabled:
        logger.info("Running initial research cycle...")
        threading.Thread(target=research_cycle, daemon=True).start()

    # Handle graceful shutdown
    shutdown_requested = threading.Event()

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        shutdown_requested.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep alive — wait for shutdown signal without traceback noise
    try:
        shutdown_requested.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()

"""Retry Manager - handles retry logic for failed research operations."""

import logging
from datetime import datetime, timezone, timedelta

from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.learning.retry_manager")


class RetryManager:
    """Manages retry logic with exponential backoff."""

    MAX_RETRIES = 5
    BASE_DELAY_MINUTES = 30

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def should_retry(self, item_id: str, error_type: str) -> bool:
        """Check if an item should be retried based on failure history."""
        # Check if there's an unresolved retry entry
        # Simple implementation: check retry_log table
        from db.connection import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM retry_log WHERE item_id = ? AND resolved = 0",
            (item_id,),
        ).fetchone()

        if not row:
            return True  # First failure, should retry

        attempt_count = row["attempt_count"]
        if attempt_count >= self.MAX_RETRIES:
            logger.warning("Item '%s' has exceeded max retries (%d)", item_id, self.MAX_RETRIES)
            return False

        # Check if enough time has passed (exponential backoff)
        next_retry = row["next_retry_at"]
        if next_retry:
            next_retry_dt = datetime.fromisoformat(next_retry)
            if datetime.now(timezone.utc) < next_retry_dt:
                return False

        return True

    def record_failure(self, item_id: str, error_type: str,
                       error_message: str = None):
        """Record a failure and calculate next retry time."""
        from db.connection import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM retry_log WHERE item_id = ? AND resolved = 0",
            (item_id,),
        ).fetchone()

        attempt = (row["attempt_count"] if row else 0) + 1
        delay = self.BASE_DELAY_MINUTES * (2 ** (attempt - 1))
        next_retry = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()

        self.repo.record_retry(item_id, error_type, error_message, next_retry)
        logger.info("Recorded failure for '%s' (attempt %d, next retry in %d min)",
                    item_id, attempt, delay)

    def record_success(self, item_id: str):
        """Mark retries as resolved after a success."""
        self.repo.resolve_retry(item_id)
        logger.info("Resolved retry log for '%s'", item_id)

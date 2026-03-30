"""Guard against modifications to critical orchestrator files."""

import logging
import os

from orchestrator.config import WEBAPP_DIR

logger = logging.getLogger("onjaro.hooks.guard")

# Files/dirs that agents must never touch (relative to PROJECT_ROOT)
PROTECTED_PATHS = [
    "orchestrator/",
    "db/",
    "agents/",
    "hooks/",
    "dashboard/",
    "data/",
    "artifacts/",
    "logs/",
    "requirements.txt",
    "CLAUDE.md",
    ".claude/",
    "start.sh",
    "setup_webapp_git.sh",
]


def is_file_protected(filepath: str) -> bool:
    """Check if a file path is outside webapp/ or in the protected list."""
    # Normalize to absolute path
    abs_path = os.path.abspath(filepath)
    webapp_abs = os.path.abspath(WEBAPP_DIR)

    # Files inside webapp/ are always allowed
    if abs_path.startswith(webapp_abs + os.sep) or abs_path == webapp_abs:
        return False

    # Everything outside webapp/ is protected
    return True


def validate_changed_files(files: list) -> tuple:
    """Validate changed files. Returns (all_safe, blocked_files)."""
    blocked = [f for f in files if is_file_protected(f)]
    if blocked:
        logger.error("Critical file guard triggered: %s", blocked)
        return False, blocked
    return True, []

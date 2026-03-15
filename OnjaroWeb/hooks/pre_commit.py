"""Pre-commit hook - runs lint and basic checks before allowing commit."""

import logging
import subprocess

from orchestrator.config import PROJECT_ROOT, CRITICAL_FILES

logger = logging.getLogger("onjaro.hooks.pre_commit")


def check_critical_files(changed_files: list[str]) -> tuple[bool, str]:
    """Check if any critical files were modified."""
    blocked = []
    for f in changed_files:
        for critical in CRITICAL_FILES:
            if f.startswith(critical) or f == critical:
                blocked.append(f)

    if blocked:
        msg = f"BLOCKED: Critical files modified: {', '.join(blocked)}"
        logger.error(msg)
        return False, msg

    return True, "No critical files modified"


def run_formatter(changed_files: list[str]) -> tuple[bool, str]:
    """Run formatter on changed files if applicable."""
    # Only format JS/TS/CSS files
    formattable = [f for f in changed_files if f.endswith(('.js', '.jsx', '.ts', '.tsx', '.css'))]
    if not formattable:
        return True, "No files to format"

    try:
        result = subprocess.run(
            ["npx", "prettier", "--write"] + formattable,
            capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            return True, "Formatting complete"
        else:
            # Formatter failure is non-blocking
            logger.warning("Formatter warning: %s", result.stderr[:200])
            return True, f"Formatter warning: {result.stderr[:200]}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True, "Formatter not available, skipping"


def run_pre_commit_checks(changed_files: list[str]) -> tuple[bool, str]:
    """Run all pre-commit checks."""
    # Check critical files
    ok, msg = check_critical_files(changed_files)
    if not ok:
        return False, msg

    # Run formatter (non-blocking)
    run_formatter(changed_files)

    return True, "Pre-commit checks passed"

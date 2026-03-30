"""Git operations manager - operates on the webapp/ subdirectory repo."""

import logging
import os
import subprocess

from orchestrator.config import (
    GIT_BRANCH,
    GIT_REMOTE,
    WEBAPP_DIR,
    TIMEOUT_GIT_OP,
)

logger = logging.getLogger("onjaro.git")


class GitError(Exception):
    pass


class GitManager:
    """Manages all git operations for the webapp/ repository."""

    def _run(self, *args, timeout: int = TIMEOUT_GIT_OP) -> str:
        """Run a git command inside WEBAPP_DIR."""
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=WEBAPP_DIR,
            )
            if result.returncode != 0:
                raise GitError(f"git {args[0]} failed: {result.stderr.strip()}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise GitError(f"git {args[0]} timed out after {timeout}s")

    def clear_lock(self) -> None:
        """Remove stale git index.lock if present in the webapp repo."""
        lock_file = os.path.join(WEBAPP_DIR, ".git", "index.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Removed stale git index.lock from webapp repo")

    def is_git_repo(self) -> bool:
        """Check if webapp/ is already a git repository."""
        return os.path.isdir(os.path.join(WEBAPP_DIR, ".git"))

    def init_repo(self) -> None:
        """Initialize a new git repo inside webapp/."""
        os.makedirs(WEBAPP_DIR, exist_ok=True)
        self._run("init", "-b", "main")
        # Set local git user so commits work without global config
        self._run("config", "user.email", "onjaro-bot@evolution.local")
        self._run("config", "user.name", "Onjaro Evolution Bot")
        logger.info("Initialized new git repo in webapp/")

    def set_remote(self, url: str) -> None:
        """Set or update the origin remote."""
        try:
            self._run("remote", "add", "origin", url)
        except GitError:
            self._run("remote", "set-url", "origin", url)
        logger.info("Remote origin set to %s", url)

    def check_clean(self) -> bool:
        """Check if the webapp working tree has no uncommitted changes."""
        status = self._run("status", "--porcelain")
        return len(status) == 0

    def get_current_branch(self) -> str:
        return self._run("branch", "--show-current")

    def get_status(self) -> dict:
        porcelain = self._run("status", "--porcelain")
        lines = [l for l in porcelain.split("\n") if l.strip()] if porcelain else []
        modified = [l[3:] for l in lines if l.startswith(" M")]
        added = [l[3:] for l in lines if l.startswith("A ") or l.startswith("??")]
        deleted = [l[3:] for l in lines if l.startswith(" D")]
        return {
            "clean": len(lines) == 0,
            "modified": modified,
            "added": added,
            "deleted": deleted,
            "total_changes": len(lines),
        }

    def get_diff(self) -> str:
        return self._run("diff")

    def get_staged_diff(self) -> str:
        return self._run("diff", "--cached")

    def get_diff_stat(self) -> str:
        return self._run("diff", "--stat")

    def stage_all(self) -> None:
        """Stage all changes in webapp/ - .gitignore handles node_modules/.next exclusions."""
        self._run("add", ".", timeout=120)

    def commit(self, run_id: str, feature_title: str, summary: str,
               screen: str = "", test_status: str = "passed") -> str:
        message = (
            f"[auto/{run_id}] {feature_title}\n\n"
            f"Summary: {summary}\n"
            f"Screen: {screen}\n"
            f"Tests: {test_status}\n"
            f"Run: {run_id}\n"
            f"\nAutonomous Evolution System"
        )
        self.stage_all()
        self._run("commit", "-m", message)
        commit_hash = self._run("rev-parse", "HEAD")
        logger.info("Committed: %s (%s)", commit_hash[:8], feature_title)
        return commit_hash

    def push(self) -> bool:
        try:
            self._run("push", GIT_REMOTE, GIT_BRANCH, timeout=60)
            logger.info("Pushed to %s/%s", GIT_REMOTE, GIT_BRANCH)
            return True
        except GitError as e:
            logger.error("Push failed: %s", e)
            return False

    def push_set_upstream(self) -> bool:
        """First push - sets upstream tracking branch."""
        try:
            self._run("push", "-u", GIT_REMOTE, GIT_BRANCH, timeout=60)
            logger.info("First push: upstream set to %s/%s", GIT_REMOTE, GIT_BRANCH)
            return True
        except GitError as e:
            logger.error("First push failed: %s", e)
            return False

    def rollback(self) -> bool:
        try:
            last_msg = self._run("log", "-1", "--pretty=%s")
            if not last_msg.startswith("[auto/"):
                logger.warning("Last commit is not ours, not rolling back")
                return False
            self._run("reset", "--hard", "HEAD~1")
            logger.info("Rolled back last commit")
            return True
        except GitError as e:
            logger.error("Rollback failed: %s", e)
            return False

    def discard_changes(self) -> None:
        self.clear_lock()
        try:
            self._run("checkout", "--", ".")
            self._run("clean", "-fd")
            logger.info("Discarded uncommitted changes in webapp/")
        except GitError as e:
            logger.error("Discard failed: %s", e)

    def get_files_changed(self) -> str:
        try:
            return self._run("diff", "--name-only", "HEAD~1", "HEAD")
        except GitError:
            return ""

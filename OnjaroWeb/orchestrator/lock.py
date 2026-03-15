"""File-based lock to prevent concurrent orchestrator runs."""

import os
import time

from orchestrator.config import LOCK_FILE, LOCK_STALE_THRESHOLD


class LockError(Exception):
    pass


class Lock:
    """File-based lock with stale detection."""

    def __init__(self):
        self.acquired = False

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)

        if os.path.exists(LOCK_FILE):
            age = time.time() - os.path.getmtime(LOCK_FILE)
            if age > LOCK_STALE_THRESHOLD:
                # Stale lock, force release
                self.release()
            else:
                try:
                    with open(LOCK_FILE, "r") as f:
                        pid = int(f.read().strip())
                    # Check if process is still alive
                    os.kill(pid, 0)
                    return False  # Process still running
                except (ValueError, ProcessLookupError, PermissionError):
                    # Process dead, stale lock
                    self.release()

        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))

        self.acquired = True
        return True

    def release(self) -> None:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

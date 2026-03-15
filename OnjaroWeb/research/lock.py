"""File-based lock to prevent concurrent research runs."""

import os
import time

from research.config import RESEARCH_LOCK_FILE, RESEARCH_LOCK_STALE_THRESHOLD


class ResearchLock:
    """File-based lock with stale detection for research runs."""

    def __init__(self):
        self.acquired = False

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(RESEARCH_LOCK_FILE), exist_ok=True)

        if os.path.exists(RESEARCH_LOCK_FILE):
            age = time.time() - os.path.getmtime(RESEARCH_LOCK_FILE)
            if age > RESEARCH_LOCK_STALE_THRESHOLD:
                self.release()
            else:
                try:
                    with open(RESEARCH_LOCK_FILE, "r") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 0)
                    return False
                except (ValueError, ProcessLookupError, PermissionError):
                    self.release()

        with open(RESEARCH_LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))

        self.acquired = True
        return True

    def release(self) -> None:
        if os.path.exists(RESEARCH_LOCK_FILE):
            os.remove(RESEARCH_LOCK_FILE)
        self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

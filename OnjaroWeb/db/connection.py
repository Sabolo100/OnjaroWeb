"""SQLite connection factory with WAL mode and thread safety."""

import os
import sqlite3
import threading
from contextlib import contextmanager

from orchestrator.config import DB_PATH

_local = threading.local()


def _get_schema_sql():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        return f.read()


def get_connection() -> sqlite3.Connection:
    """Get or create a thread-local SQLite connection."""
    if not hasattr(_local, "connection") or _local.connection is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connection = conn
    return _local.connection


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    conn.executescript(_get_schema_sql())
    conn.commit()


@contextmanager
def transaction():
    """Context manager for database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

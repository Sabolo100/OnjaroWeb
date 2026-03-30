"""Supabase client singleton for project content database."""

import logging

from research.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

logger = logging.getLogger("onjaro.research.supabase")

_client = None


def get_supabase_client():
    """Get or create the Supabase client (singleton)."""
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.error(
            "Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars."
        )
        return None

    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase client initialized: %s", SUPABASE_URL)
        return _client
    except ImportError:
        logger.error("supabase package required. pip install supabase")
        return None
    except Exception as e:
        logger.error("Failed to create Supabase client: %s", e)
        return None


def reset_client():
    """Reset the singleton client (for testing)."""
    global _client
    _client = None

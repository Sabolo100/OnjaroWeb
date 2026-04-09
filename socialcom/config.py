"""Configuration for the socialcom module."""

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Supabase ────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ── AI content generation ───────────────────────────────────────────
# Perplexity is used for content generation (same API as research)
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.environ.get("SOCIALCOM_AI_MODEL", "sonar")

# ── LinkedIn ────────────────────────────────────────────────────────
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_ORG_ID = os.environ.get("LINKEDIN_ORG_ID", "")

# ── Mailchimp ───────────────────────────────────────────────────────
MAILCHIMP_API_KEY = os.environ.get("MAILCHIMP_API_KEY", "")
MAILCHIMP_SERVER_PREFIX = os.environ.get("MAILCHIMP_SERVER_PREFIX", "")
MAILCHIMP_LIST_ID = os.environ.get("MAILCHIMP_LIST_ID", "")
MAILCHIMP_FROM_NAME = os.environ.get("MAILCHIMP_FROM_NAME", "FMintel")
MAILCHIMP_FROM_EMAIL = os.environ.get("MAILCHIMP_FROM_EMAIL", "")

# ── Email (SMTP) ────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "FMintel")

# ── Facebook ────────────────────────────────────────────────────────
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")

# ── Scheduling ──────────────────────────────────────────────────────
SOCIALCOM_ENABLED = bool(int(os.environ.get("SOCIALCOM_ENABLED", "0")))
SOCIALCOM_INTERVAL_MINUTES = int(os.environ.get("SOCIALCOM_INTERVAL_MINUTES", "60"))

# ── Progress tracking ──────────────────────────────────────────────
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "data", ".socialcom_progress.json")

# ── Retry settings ──────────────────────────────────────────────────
MAX_PUBLISH_RETRIES = 3
RETRY_DELAY_SECONDS = 30

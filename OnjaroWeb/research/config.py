"""Configuration for the research orchestration module."""

import os

from orchestrator.config import PROJECT_ROOT, WEBAPP_DIR, DB_PATH

# Research scheduling - default: daily (1440 minutes)
RESEARCH_RUN_INTERVAL_MINUTES = int(os.environ.get("RESEARCH_INTERVAL_MINUTES", "1440"))

# Lock
RESEARCH_LOCK_FILE = os.path.join(PROJECT_ROOT, "data", ".research.lock")
RESEARCH_LOCK_STALE_THRESHOLD = 3600  # 60 minutes

# Artifacts
RESEARCH_ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts", "research")
RESEARCH_PROMPTS_DIR = os.path.join(PROJECT_ROOT, "research", "agents", "prompts")

# Project-specific config location (lives inside webapp repo)
RESEARCH_CONFIG_DIR = os.path.join(WEBAPP_DIR, "research_config")

# AI platform for research: "perplexity", "openai", "gemini", "claude"
RESEARCH_AI_PLATFORM = os.environ.get("RESEARCH_AI_PLATFORM", "perplexity")

# Perplexity
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar")
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

# OpenAI (for future use)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# Supabase (project content database)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Per-agent budgets (USD)
BUDGET_RESEARCH_PLANNER = 0.30
BUDGET_EXTRACTOR = 0.50
BUDGET_VALIDATOR = 0.20
BUDGET_DEDUPE = 0.20
BUDGET_PERSISTENCE = 0.10
BUDGET_EVALUATOR = 0.30
RESEARCH_DAILY_BUDGET_CAP = 5.00

# Timeouts (seconds)
TIMEOUT_RESEARCH_PLANNER = 120
TIMEOUT_RESEARCH_FETCH = 60
TIMEOUT_RESEARCH_EXTRACT = 120
TIMEOUT_RESEARCH_VALIDATE = 60
TIMEOUT_RESEARCH_DEDUPE = 60
TIMEOUT_RESEARCH_PERSIST = 30

# Confidence thresholds
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_AUTO_APPROVE_ABOVE = 0.8
DEFAULT_MANUAL_REVIEW_BELOW = 0.4

# Fetch settings
MAX_RESULTS_PER_QUERY = 10
FETCH_TIMEOUT_SECONDS = 30
FETCH_RETRY_COUNT = 3

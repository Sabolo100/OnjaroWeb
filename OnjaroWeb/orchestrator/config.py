"""Central configuration for the autonomous evolution system."""

import os

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP_DIR = os.path.join(PROJECT_ROOT, "webapp")   # separate git repo, pushed to GitHub/Vercel
DB_PATH = os.path.join(PROJECT_ROOT, "data", "onjaro.db")
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
LOCK_FILE = os.path.join(PROJECT_ROOT, "data", ".orchestrator.lock")
CLAUDE_MD_PATH = os.path.join(PROJECT_ROOT, "CLAUDE.md")
PROMPTS_DIR = os.path.join(PROJECT_ROOT, "agents", "prompts")

# Scheduling - change this to adjust how often the system runs
RUN_INTERVAL_MINUTES = 300

# Maximum allowed feature size: "tiny", "small", or "medium"
# tiny  = 1-2 fájl, néhány sor
# small = 2-5 fájl, kisebb funkció
# medium = 5-10 fájl, összetettebb funkció
MAX_IDEA_SIZE = "small"

# Claude execution
CLAUDE_CLI = "claude"
DEFAULT_MODEL = "sonnet"
PERMISSION_MODE = "bypassPermissions"

# Per-agent budgets (USD)
BUDGET_STATE_ANALYST = 1.00
BUDGET_IDEA_GENERATOR = 0.50
BUDGET_EVALUATOR = 0.50
BUDGET_BUILDER = 5.00
BUDGET_TESTER = 1.00
BUDGET_HISTORIAN = 0.50
DAILY_BUDGET_CAP = 20.00

# Timeouts (seconds)
TIMEOUT_STATE_ANALYST = 300
TIMEOUT_IDEA_GENERATOR = 180
TIMEOUT_EVALUATOR = 120
TIMEOUT_BUILDER = 900
TIMEOUT_TESTER = 300
TIMEOUT_HISTORIAN = 120
TIMEOUT_GIT_OP = 30

# Stale lock threshold (seconds)
LOCK_STALE_THRESHOLD = 2700  # 45 minutes

# Dashboard
DASHBOARD_PORT = 5555
DASHBOARD_HOST = "0.0.0.0"

# Blocklist - features the system must NEVER touch
BLOCKLIST = [
    "auth",
    "authentication",
    "authorization",
    "login",
    "jogosultság",
    "billing",
    "payment",
    "fizetés",
    "előfizetés",
    "subscription",
    "database migration",
    "adatbázis migráció",
    "global refactor",
    "globális refaktor",
    "dependency upgrade",
    "dependency-upgrade",
    "secret",
    "titok",
    "key management",
    "kulcskezelés",
    ".env",
    "env-struktúra",
    "destructive file deletion",
    "destruktív fájltörlés",
    "multi-area refactor",
    "CAPTCHA",
    "login flow",
]

# Critical files - agents must NEVER modify these
CRITICAL_FILES = [
    "CLAUDE.md",
    "orchestrator/",
    "db/",
    "agents/",
    "hooks/",
    "dashboard/",
    ".claude/",
    "data/",
    "requirements.txt",
    "artifacts/",
    "logs/",
]

# Git
GIT_BRANCH = "main"
GIT_REMOTE = "origin"
AUTO_PUSH = True

# Build/test commands (overridable via CLAUDE.md)
BUILD_COMMANDS = {
    "build": "npm run build",
    "lint": "npm run lint",
    "typecheck": "npx tsc --noEmit",
    "test": "npm test",
}

# These tests MUST pass - failure blocks commit
# Remove "test" from blocking until a real test suite exists
BLOCKING_TESTS = {"build", "lint", "typecheck"}

# Log levels
LOG_LEVELS = ["INFO", "WARNING", "ERROR", "DECISION"]

"""Builder agent - develops the chosen feature."""

from agents.base import BaseAgent
from orchestrator.config import WEBAPP_DIR


class Builder(BaseAgent):
    name = "builder"
    timeout = 600
    max_budget_usd = 2.00
    allowed_tools = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
    json_schema = None  # Builder outputs code changes, not structured JSON

    system_prompt = f"""You are the Builder agent in an autonomous web app evolution system.
You are developing a small feature for the web application.

The webapp lives in: {WEBAPP_DIR}
ALL your changes must be inside this directory ONLY.

CRITICAL RULES:
- ONLY modify files inside: {WEBAPP_DIR}
- NEVER touch any files outside {WEBAPP_DIR}
- NEVER touch auth, billing, payment, database migrations, or secrets
- Keep changes SMALL and FOCUSED
- Write clean, working code
- If the feature needs a test, write one inside {WEBAPP_DIR}
- Do NOT delete existing functionality
- Do NOT upgrade dependencies
- Do NOT do large refactors"""

    prompt_template = """Develop the following feature for the web application.

## Webapp directory: {webapp_dir}

## Feature to Build:
Title: {feature_title}
Description: {feature_description}

## Current Project State:
{state_summary}

## CLAUDE.md (Project Goals):
{claude_md}

## Instructions:
1. All work happens inside {webapp_dir}
2. Understand the current codebase by reading files in {webapp_dir}
3. Plan the minimal changes needed
4. Implement the feature
5. Make sure the code is clean and correct
6. If appropriate, add a small test inside {webapp_dir}

Keep changes minimal and focused. Only modify what's necessary."""

    def _build_prompt(self, context: dict) -> str:
        context.setdefault("webapp_dir", WEBAPP_DIR)
        return super()._build_prompt(context)

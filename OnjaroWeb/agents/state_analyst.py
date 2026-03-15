"""State Analyst agent - maps the current project state."""

from agents.base import BaseAgent


class StateAnalyst(BaseAgent):
    name = "state_analyst"
    timeout = 120
    max_budget_usd = 0.30
    allowed_tools = ["Read", "Glob", "Grep", "Bash(git:*)", "Bash(ls:*)"]

    json_schema = {
        "type": "object",
        "properties": {
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "screens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "route": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "components": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tech_stack": {
                "type": "object",
                "properties": {
                    "framework": {"type": "string"},
                    "language": {"type": "string"},
                    "styling": {"type": "string"},
                },
            },
            "gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of logical gaps, broken links, missing data, incomplete features",
            },
            "state_summary": {"type": "string"},
        },
        "required": ["routes", "screens", "components", "gaps", "state_summary"],
    }

    prompt_template = """You are the State Analyst agent in an autonomous web app evolution system.

Your job: analyze the current state of the web application.

## Webapp directory: {webapp_dir}

## CLAUDE.md (Project Constitution):
{claude_md}

## Currently Live Features:
{live_features}

## Known Screens:
{known_screens}

## Instructions:
1. Read files inside {webapp_dir} to understand the current structure
2. Identify all routes, screens, and key components
3. Note the tech stack (framework, language, styling approach)
4. Create a concise state summary

Return a JSON object with: routes, screens, components, tech_stack, state_summary.
Focus on what EXISTS now, not what should exist."""

    def _build_prompt(self, context: dict) -> str:
        from orchestrator.config import WEBAPP_DIR
        context.setdefault("webapp_dir", WEBAPP_DIR)
        return super()._build_prompt(context)

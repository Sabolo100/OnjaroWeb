"""Historian agent - creates structured run summaries."""

from agents.base import BaseAgent


class Historian(BaseAgent):
    name = "historian"
    timeout = 60
    max_budget_usd = 0.15
    allowed_tools = []

    json_schema = {
        "type": "object",
        "properties": {
            "run_summary": {"type": "string"},
            "feature_description": {"type": "string"},
            "files_changed": {
                "type": "array",
                "items": {"type": "string"},
            },
            "decisions_made": {"type": "string"},
            "issues_encountered": {"type": "string"},
            "quality_score": {"type": "number"},
        },
        "required": ["run_summary", "feature_description", "files_changed", "decisions_made"],
    }

    prompt_template = """You are the Historian agent in an autonomous web app evolution system.

Your job: create a structured summary of this completed development run.

## Run ID: {run_id}
## Feature Built: {feature_title}
## Feature Description: {feature_description}

## Events during this run:
{run_events}

## Test Results:
{test_results}

## Files Changed:
{files_changed}

## Decision Rationale:
{decision_rationale}

## Instructions:
Create a concise, structured summary that captures:
1. What was built and why
2. Key files that were changed
3. Important decisions made during the run
4. Any issues encountered
5. Overall quality assessment (1-10)

This summary will be stored for future reference to help the system understand its own history."""

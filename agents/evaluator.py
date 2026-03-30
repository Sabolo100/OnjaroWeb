"""Evaluator agent - scores and picks the best feature idea."""

from agents.base import BaseAgent


class Evaluator(BaseAgent):
    name = "evaluator"
    timeout = 60
    max_budget_usd = 0.15
    allowed_tools = []

    json_schema = {
        "type": "object",
        "properties": {
            "chosen": {
                "type": "object",
                "properties": {
                    "idea_index": {"type": "integer"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["idea_index", "score", "rationale"],
            },
            "rejected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "idea_index": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        "required": ["chosen", "rejected"],
    }

    prompt_template = """You are the Evaluator agent in an autonomous web app evolution system.

Your job: evaluate 3 feature ideas and pick the BEST one to implement.

## CLAUDE.md (Project Constitution):
{claude_md}

## Current State:
{state_summary}

## The 3 Ideas:
{ideas_json}

## Evaluation Criteria (in order of importance):
1. **Safety**: Low regression risk, doesn't touch critical systems
2. **Testability**: Can be verified automatically
3. **Size**: Smaller is better - prefer "tiny" over "medium"
4. **Value**: Aligns with product goals in CLAUDE.md
5. **Independence**: Doesn't depend on unbuilt features
6. **Novelty**: Not a duplicate of existing features

## Output:
- chosen: the best idea (idea_index 0-2, score 1-100, rationale)
- rejected: the other two with reasons for rejection"""

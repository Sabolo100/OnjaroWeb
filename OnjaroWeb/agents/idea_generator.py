"""Idea Generator agent - proposes 3 small feature ideas."""

from agents.base import BaseAgent


class IdeaGenerator(BaseAgent):
    name = "idea_generator"
    timeout = 90
    max_budget_usd = 0.20
    allowed_tools = []

    json_schema = {
        "type": "object",
        "properties": {
            "ideas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "rationale": {"type": "string"},
                        "estimated_size": {
                            "type": "string",
                            "enum": ["tiny", "small", "medium"],
                        },
                        "testability_score": {"type": "number"},
                        "affected_screen": {"type": "string"},
                    },
                    "required": ["title", "description", "rationale", "estimated_size", "testability_score"],
                },
                "minItems": 3,
                "maxItems": 3,
            },
        },
        "required": ["ideas"],
    }

    prompt_template = """You are the Idea Generator agent in an autonomous web app evolution system.

Your job: propose exactly 3 small, new feature ideas for the web application.

## CLAUDE.md (Project Constitution):
{claude_md}

## Current State Summary:
{state_summary}

## Already Live Features:
{live_features}

## Recently Rejected/Failed Ideas:
{recent_ideas}

## BLOCKLIST - You must NEVER suggest anything related to:
{blocklist}

## Rules:
1. Each idea must be SMALL - implementable in a single iteration
2. Each idea must be TESTABLE - can be verified with build/lint/test
3. Each idea must ALIGN with the CLAUDE.md product goals
4. Each idea must NOT duplicate an existing live feature
5. Each idea must NOT touch blocked categories
6. Prefer additive features over modifications to existing ones
7. Prefer UI enhancements, new small components, quality-of-life improvements

## Output:
Return exactly 3 ideas, each with:
- title: short feature name
- description: what it does (2-3 sentences)
- rationale: why this improves the app
- estimated_size: "tiny", "small", or "medium"
- testability_score: 1-10 (10 = easiest to test)
- affected_screen: which screen/route this affects"""

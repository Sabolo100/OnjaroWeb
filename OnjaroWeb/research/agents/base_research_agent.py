"""Base agent class for research-specific subagents."""

import json
import logging
import os
import time

from orchestrator.event_bus import EventBus
from db.research_repository import ResearchRepository
from research.config import RESEARCH_ARTIFACTS_DIR, RESEARCH_PROMPTS_DIR

logger = logging.getLogger("onjaro.research.agents")


class ResearchAgentError(Exception):
    pass


class BaseResearchAgent:
    """Base class for all research subagents.

    Unlike evolution agents that use Claude CLI, research agents
    can use configurable AI platforms (Perplexity, OpenAI, etc.)
    via their respective API clients.
    """

    name: str = "base_research"
    prompt_template: str = ""
    timeout: int = 120
    max_budget_usd: float = 0.30

    def __init__(self, repo: ResearchRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    def run(self, run_id: str, context: dict) -> dict:
        """Execute this agent's task and return structured result."""
        prompt = self._build_prompt(context)
        phase = self._get_phase()

        self.event_bus.emit(
            run_id=run_id, phase=phase, agent_name=self.name,
            severity="INFO", event_type="research_agent_start",
            message=f"Starting {self.name}",
        )

        self._save_artifact(run_id, "prompt", prompt)
        start_time = time.time()

        try:
            result = self._execute(prompt, context)
            duration_ms = int((time.time() - start_time) * 1000)

            if result.get("cost_usd"):
                self.repo.update_research_cost(run_id, result["cost_usd"])

            self._save_artifact(run_id, "output",
                                json.dumps(result, default=str, ensure_ascii=False))

            self.repo.log_research_event(
                run_id=run_id, phase=phase, agent_name=self.name,
                severity="INFO", event_type="research_agent_complete",
                message=f"{self.name} completed in {duration_ms}ms",
                duration_ms=duration_ms,
            )

            self.event_bus.emit(
                run_id=run_id, phase=phase, agent_name=self.name,
                severity="INFO", event_type="research_agent_complete",
                message=f"{self.name} completed in {duration_ms}ms",
                data={"duration_ms": duration_ms, "cost_usd": result.get("cost_usd", 0)},
            )

            return self._parse_result(result)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.event_bus.emit(
                run_id=run_id, phase=phase, agent_name=self.name,
                severity="ERROR", event_type="research_agent_failed",
                message=f"{self.name} failed: {e}",
            )
            raise ResearchAgentError(f"{self.name} failed: {e}") from e

    def _execute(self, prompt: str, context: dict) -> dict:
        """Execute the AI call. Override in subclasses for specific platforms."""
        raise NotImplementedError("Subclasses must implement _execute()")

    def _build_prompt(self, context: dict) -> str:
        """Load prompt template and fill in context variables."""
        template = self._load_template()
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning("Missing prompt context key: %s", e)
            return template

    def _load_template(self) -> str:
        """Load the prompt template from file."""
        path = os.path.join(RESEARCH_PROMPTS_DIR, f"{self.name}.md")
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        return self.prompt_template

    def _parse_result(self, result: dict) -> dict:
        """Parse the AI result into structured data."""
        content = result.get("result", "")
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                inner = "\n".join(lines[1:])
                if "```" in inner:
                    inner = inner[:inner.rfind("```")]
                cleaned = inner.strip()
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, TypeError):
                import re
                json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except (json.JSONDecodeError, TypeError):
                        pass
                return {"raw_text": content}
        return {"raw_text": str(content)}

    def _save_artifact(self, run_id: str, artifact_type: str, content: str) -> str:
        """Save an artifact to disk."""
        run_dir = os.path.join(RESEARCH_ARTIFACTS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)

        filename = f"{self.name}_{artifact_type}.txt"
        path = os.path.join(run_dir, filename)

        with open(path, "w") as f:
            f.write(content)

        return path

    def _get_phase(self) -> str:
        """Map agent name to research phase."""
        return {
            "research_planner": "PLANNING",
            "source_selector": "PLANNING",
            "extractor": "EXTRACTING",
            "validator": "VALIDATING",
            "dedupe": "DEDUPING",
            "persistence_decision": "PERSISTING",
            "research_evaluator": "COMPLETED",
        }.get(self.name, self.name.upper())

"""Base agent class for all subagents."""

import json
import logging
import os
import time

from orchestrator.claude_executor import ClaudeExecutor
from orchestrator.event_bus import EventBus
from orchestrator.config import PROMPTS_DIR, ARTIFACTS_DIR
from db.repository import Repository

logger = logging.getLogger("onjaro.agents")


class AgentError(Exception):
    pass


class BaseAgent:
    """Base class for all evolution subagents."""

    name: str = "base"
    prompt_template: str = ""
    json_schema: dict = None
    allowed_tools: list = None
    timeout: int = 120
    max_budget_usd: float = 0.30
    system_prompt: str = None

    def __init__(self, executor: ClaudeExecutor, repo: Repository, event_bus: EventBus):
        self.executor = executor
        self.repo = repo
        self.event_bus = event_bus

    def run(self, run_id: str, context: dict) -> dict:
        """Execute this agent's task and return structured result."""
        prompt = self._build_prompt(context)
        phase = self._get_phase()

        # Emit start event
        self.event_bus.emit(
            run_id=run_id, phase=phase, agent_name=self.name,
            severity="INFO", event_type="agent_start",
            message=f"Starting {self.name}",
        )

        # Save prompt artifact
        self._save_artifact(run_id, "prompt", prompt)

        start_time = time.time()

        # Execute Claude
        result = self.executor.execute(
            prompt=prompt,
            system_prompt=self.system_prompt,
            json_schema=self.json_schema,
            allowed_tools=self.allowed_tools,
            timeout=self.timeout,
            max_budget_usd=self.max_budget_usd,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # Update run cost
        if result.get("cost_usd"):
            self.repo.update_run_cost(run_id, result["cost_usd"])

        # Save output artifact
        self._save_artifact(run_id, "output", json.dumps(result, default=str, ensure_ascii=False))

        if not result["success"]:
            self.event_bus.emit(
                run_id=run_id, phase=phase, agent_name=self.name,
                severity="ERROR", event_type="agent_failed",
                message=f"{self.name} failed: {result.get('error', 'unknown')}",
            )
            raise AgentError(f"{self.name} failed: {result.get('error', 'unknown')}")

        # Log event to DB
        self.repo.log_event(
            run_id=run_id, phase=phase, agent_name=self.name,
            severity="INFO", event_type="agent_complete",
            message=f"{self.name} completed successfully",
            duration_ms=duration_ms,
        )

        self.event_bus.emit(
            run_id=run_id, phase=phase, agent_name=self.name,
            severity="INFO", event_type="agent_complete",
            message=f"{self.name} completed in {duration_ms}ms",
            data={"duration_ms": duration_ms, "cost_usd": result.get("cost_usd", 0)},
        )

        return self._parse_result(result)

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
        path = os.path.join(PROMPTS_DIR, f"{self.name}.md")
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        # Fallback to inline template
        return self.prompt_template

    def _parse_result(self, result: dict) -> dict:
        """Parse the Claude result into structured data."""
        content = result.get("result", "")
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            # Strip markdown code fences if present (```json ... ```)
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first line (```json or ```) and last line (```)
                inner = "\n".join(lines[1:])
                if "```" in inner:
                    inner = inner[:inner.rfind("```")]
                cleaned = inner.strip()
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, TypeError):
                # Try to find a JSON object or array anywhere in the text
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
        """Save an artifact to disk and register in DB."""
        run_dir = os.path.join(ARTIFACTS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)

        filename = f"{self.name}_{artifact_type}.txt"
        path = os.path.join(run_dir, filename)

        with open(path, "w") as f:
            f.write(content)

        size = os.path.getsize(path)
        self.repo.save_artifact(run_id, f"{self.name}_{artifact_type}", path, size)
        return path

    def _get_phase(self) -> str:
        """Map agent name to run phase."""
        return {
            "state_analyst": "STATE_ANALYSIS",
            "idea_generator": "IDEA_GENERATION",
            "evaluator": "EVALUATION",
            "builder": "BUILD",
            "tester": "TEST",
            "historian": "HISTORY",
        }.get(self.name, self.name.upper())

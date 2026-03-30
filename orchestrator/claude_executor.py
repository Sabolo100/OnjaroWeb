"""Claude CLI wrapper for headless execution."""

import json
import logging
import subprocess
import time
from typing import Generator

from orchestrator.config import (
    CLAUDE_CLI,
    DEFAULT_MODEL,
    PERMISSION_MODE,
    PROJECT_ROOT,
)

logger = logging.getLogger("onjaro.claude")


class ClaudeExecutionError(Exception):
    pass


class ClaudeExecutor:
    """Wraps the Claude CLI for non-interactive execution."""

    def __init__(self, model: str = None):
        self.model = model or DEFAULT_MODEL

    def execute(
        self,
        prompt: str,
        system_prompt: str = None,
        json_schema: dict = None,
        allowed_tools: list = None,
        timeout: int = 300,
        max_budget_usd: float = 0.50,
    ) -> dict:
        """Execute a Claude CLI call and return structured result."""
        cmd = self._build_command(
            prompt, system_prompt, json_schema, allowed_tools, max_budget_usd
        )

        logger.info("Executing Claude: %s", " ".join(cmd[:5]) + "...")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=PROJECT_ROOT,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                stderr = result.stderr[:2000]
                logger.error("Claude CLI error (rc=%d): %s", result.returncode, stderr[:500])
                # Classify the error type for clearer dashboard messages
                stderr_lower = stderr.lower()
                if any(k in stderr_lower for k in ("budget", "cost", "credit", "billing", "limit exceeded")):
                    error_type = "BUDGET_EXCEEDED"
                    error_msg = f"Budget/kredit limit elérve: {stderr[:300]}"
                elif any(k in stderr_lower for k in ("rate limit", "429", "too many requests")):
                    error_type = "RATE_LIMITED"
                    error_msg = f"API rate limit: {stderr[:300]}"
                elif any(k in stderr_lower for k in ("unauthorized", "401", "api key", "authentication")):
                    error_type = "AUTH_ERROR"
                    error_msg = f"API hitelesítési hiba: {stderr[:300]}"
                elif any(k in stderr_lower for k in ("network", "connection", "timeout", "unreachable")):
                    error_type = "NETWORK_ERROR"
                    error_msg = f"Hálózati hiba: {stderr[:300]}"
                else:
                    error_type = "CLI_ERROR"
                    error_msg = stderr[:2000]
                return {
                    "success": False,
                    "result": None,
                    "error": error_msg,
                    "error_type": error_type,
                    "cost_usd": 0.0,
                    "duration_ms": duration_ms,
                    "raw": None,
                }

            # Parse JSON output
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                # If not valid JSON, treat stdout as plain text result
                parsed = {"result": result.stdout.strip(), "is_error": False}

            cost_usd = parsed.get("total_cost_usd", parsed.get("cost_usd", 0.0)) or 0.0
            is_error = parsed.get("is_error", False)
            result_content = parsed.get("result", result.stdout.strip())

            # Try to parse result_content as JSON if it looks like it
            if isinstance(result_content, str):
                try:
                    result_content = json.loads(result_content)
                except (json.JSONDecodeError, TypeError):
                    pass

            return {
                "success": not is_error,
                "result": result_content,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
                "raw": parsed,
            }

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error("Claude CLI timed out after %ds", timeout)
            return {
                "success": False,
                "result": None,
                "error": f"Időtúllépés: az agent nem válaszolt {timeout}s alatt (nem kredit-hiány – valószínűleg lassú API vagy nagy kontextus)",
                "error_type": "TIMEOUT",
                "cost_usd": 0.0,
                "duration_ms": duration_ms,
                "raw": None,
            }

    def execute_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        allowed_tools: list = None,
        timeout: int = 300,
        max_budget_usd: float = 0.50,
    ) -> Generator[dict, None, None]:
        """Execute Claude CLI with streaming JSON output."""
        cmd = self._build_command(
            prompt, system_prompt, None, allowed_tools, max_budget_usd,
            output_format="stream-json",
        )
        cmd.append("--verbose")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT,
        )

        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    yield event
                except json.JSONDecodeError:
                    yield {"type": "raw", "content": line}

            process.wait(timeout=10)
        except Exception as e:
            process.kill()
            raise ClaudeExecutionError(f"Stream error: {e}")

    def _build_command(
        self,
        prompt: str,
        system_prompt: str = None,
        json_schema: dict = None,
        allowed_tools: list = None,
        max_budget_usd: float = 0.50,
        output_format: str = "json",
    ) -> list:
        cmd = [
            CLAUDE_CLI,
            "-p", prompt,
            "--output-format", output_format,
            "--model", self.model,
            "--permission-mode", PERMISSION_MODE,
            "--max-turns", "50",
        ]

        if max_budget_usd:
            cmd.extend(["--max-budget-usd", str(max_budget_usd)])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        # Note: --json-schema is not a Claude CLI flag.
        # JSON structure is enforced via the prompt itself (see agent prompts).

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        return cmd

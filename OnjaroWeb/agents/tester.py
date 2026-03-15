"""Tester agent - runs build, lint, typecheck, and tests."""

import json
import logging
import subprocess
import time

from orchestrator.config import BUILD_COMMANDS, WEBAPP_DIR, BLOCKING_TESTS
from orchestrator.event_bus import EventBus
from db.repository import Repository

logger = logging.getLogger("onjaro.agents.tester")


class Tester:
    """Runs deterministic test commands without Claude."""

    name = "tester"

    def __init__(self, repo: Repository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    def run(self, run_id: str, context: dict = None) -> dict:
        """Run all test commands and return results."""
        self.event_bus.emit(
            run_id=run_id, phase="TEST", agent_name=self.name,
            severity="INFO", event_type="agent_start",
            message="Starting test suite",
        )

        results = []
        all_passed = True

        for test_type, command in BUILD_COMMANDS.items():
            start = time.time()
            passed, output = self._run_command(command)
            duration_ms = int((time.time() - start) * 1000)

            results.append({
                "type": test_type,
                "passed": passed,
                "output": output[:5000],  # Truncate long outputs
                "duration_ms": duration_ms,
            })

            # Save to DB
            self.repo.save_test(run_id, test_type, passed, output[:2000], duration_ms)

            self.event_bus.emit(
                run_id=run_id, phase="TEST", agent_name=self.name,
                severity="INFO" if passed else "ERROR",
                event_type="test_result",
                message=f"{test_type}: {'PASS' if passed else 'FAIL'}",
                data={"test_type": test_type, "passed": passed, "duration_ms": duration_ms},
            )

            if not passed:
                if test_type in BLOCKING_TESTS:
                    all_passed = False
                    logger.warning("Blocking test failed: %s", test_type)
                else:
                    logger.warning("Non-blocking test failed (ignored): %s", test_type)

        summary = "All tests passed" if all_passed else "Some tests failed"

        self.event_bus.emit(
            run_id=run_id, phase="TEST", agent_name=self.name,
            severity="INFO" if all_passed else "ERROR",
            event_type="agent_complete",
            message=summary,
            data={"all_passed": all_passed, "results": [r["type"] + ":" + ("PASS" if r["passed"] else "FAIL") for r in results]},
        )

        self.repo.log_event(
            run_id=run_id, phase="TEST", agent_name=self.name,
            severity="INFO" if all_passed else "ERROR",
            event_type="test_complete", message=summary,
        )

        return {
            "tests": results,
            "all_passed": all_passed,
            "summary": summary,
        }

    def _run_command(self, command: str) -> tuple[bool, str]:
        """Run a shell command and return (passed, output)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=WEBAPP_DIR,
            )
            output = result.stdout + "\n" + result.stderr
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, f"Command timed out: {command}"
        except Exception as e:
            return False, f"Command error: {e}"

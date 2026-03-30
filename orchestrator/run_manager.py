"""Run Manager - the central state machine for evolution cycles."""

import json
import logging
import time
import traceback
from uuid import uuid4

from orchestrator.config import (
    BLOCKLIST,
    CLAUDE_MD_PATH,
    AUTO_PUSH,
    DAILY_BUDGET_CAP,
    PROJECT_ROOT,
    WEBAPP_DIR,
    MAX_IDEA_SIZE,
)
from orchestrator.event_bus import EventBus
from orchestrator.claude_executor import ClaudeExecutor
from orchestrator.git_manager import GitManager, GitError
from db.repository import Repository
from agents.state_analyst import StateAnalyst
from agents.idea_generator import IdeaGenerator
from agents.evaluator import Evaluator
from agents.builder import Builder
from agents.tester import Tester
from agents.historian import Historian
from agents.bootstrapper import Bootstrapper
from agents.base import AgentError
from hooks.pre_commit import run_pre_commit_checks
from hooks.artifact_saver import save_error_artifact, save_json_artifact

logger = logging.getLogger("onjaro.run_manager")


class RunError(Exception):
    pass


class TestFailure(Exception):
    def __init__(self, test_result: dict):
        self.test_result = test_result
        super().__init__(f"Tests failed: {test_result.get('summary', 'unknown')}")


class RunManager:
    """Manages the full lifecycle of an evolution run."""

    def __init__(
        self,
        executor: ClaudeExecutor,
        repo: Repository,
        event_bus: EventBus,
        git_manager: GitManager,
    ):
        self.executor = executor
        self.repo = repo
        self.event_bus = event_bus
        self.git = git_manager

        # Initialize agents
        self.state_analyst = StateAnalyst(executor, repo, event_bus)
        self.idea_generator = IdeaGenerator(executor, repo, event_bus)
        self.evaluator = Evaluator(executor, repo, event_bus)
        self.builder = Builder(executor, repo, event_bus)
        self.tester = Tester(repo, event_bus)
        self.historian = Historian(executor, repo, event_bus)
        self.bootstrapper = Bootstrapper(executor, repo, event_bus)

    def _needs_bootstrap(self) -> bool:
        """Check if the webapp needs bootstrapping (no webapp/package.json yet)."""
        import os
        return not os.path.exists(os.path.join(WEBAPP_DIR, "package.json"))

    def execute_bootstrap(self) -> str:
        """Create the initial webapp from CLAUDE.md. Returns run_id."""
        run_id = "bootstrap_" + uuid4().hex[:8]
        start_time = time.time()

        self.repo.create_run(run_id)
        self.event_bus.emit(
            run_id=run_id, phase="BOOTSTRAP", agent_name="orchestrator",
            severity="INFO", event_type="run_start",
            message="Bootstrap: creating initial webapp from CLAUDE.md",
        )

        try:
            self._advance_phase(run_id, "BOOTSTRAP")
            claude_md = self._read_claude_md()

            # Ensure webapp git repo exists
            import os
            os.makedirs(WEBAPP_DIR, exist_ok=True)
            if not self.git.is_git_repo():
                self.git.init_repo()
                logger.info("Initialized webapp git repo at %s", WEBAPP_DIR)

            self.bootstrapper.run(run_id, {"claude_md": claude_md})

            # Verify bootstrap succeeded
            if self._needs_bootstrap():
                raise RunError("Bootstrap completed but package.json still missing")

            # Commit the initial state
            if not self.git.check_clean():
                commit_hash = self.git.commit(
                    run_id=run_id,
                    feature_title="Initial webapp bootstrap",
                    summary="Created initial webapp from CLAUDE.md",
                    screen="all",
                    test_status="bootstrap",
                )
                self.repo.save_git_history(run_id, commit_hash, "Bootstrap: initial webapp", "")
                if AUTO_PUSH:
                    # First push needs -u to set upstream
                    self.git.push_set_upstream()

            duration_ms = int((time.time() - start_time) * 1000)
            self.repo.complete_run(run_id, duration_ms)

            self.event_bus.emit(
                run_id=run_id, phase="BOOTSTRAP", agent_name="orchestrator",
                severity="INFO", event_type="run_complete",
                message="Bootstrap completed - initial webapp created",
                data={"duration_ms": duration_ms},
            )

            logger.info("Bootstrap completed in %ds", duration_ms / 1000)
            return run_id

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Bootstrap failed: %s\n%s", e, tb)
            self.repo.update_run_status(run_id, "FAILED", str(e)[:500])
            self.event_bus.emit(
                run_id=run_id, phase="BOOTSTRAP", agent_name="orchestrator",
                severity="ERROR", event_type="run_failed",
                message=f"Bootstrap failed: {str(e)[:200]}",
            )
            return run_id

    def execute_run(self) -> str:
        """Execute a full evolution cycle. Returns run_id."""
        # Check if bootstrap is needed first
        if self._needs_bootstrap():
            logger.info("No webapp detected - running bootstrap first")
            bootstrap_run_id = self.execute_bootstrap()
            if self._needs_bootstrap():
                logger.error("Bootstrap failed, skipping evolution cycle")
                return bootstrap_run_id

        run_id = uuid4().hex[:12]
        start_time = time.time()

        # Check daily budget
        daily_cost = self.repo.get_daily_cost()
        if daily_cost >= DAILY_BUDGET_CAP:
            logger.warning("Daily budget cap reached ($%.2f). Skipping run.", daily_cost)
            return None

        # Create run record
        self.repo.create_run(run_id)

        self.event_bus.emit(
            run_id=run_id, phase="INIT", agent_name="orchestrator",
            severity="INFO", event_type="run_start",
            message=f"Starting evolution run {run_id}",
        )

        try:
            # Check git state
            if not self.git.check_clean():
                self.git.discard_changes()
                if not self.git.check_clean():
                    raise RunError("Cannot clean working tree")

            # === Phase 1: State Analysis ===
            self._advance_phase(run_id, "STATE_ANALYSIS")
            claude_md = self._read_claude_md()
            live_features = self.repo.get_live_features(limit=50)
            known_screens = self.repo.get_screens()

            state = self.state_analyst.run(run_id, {
                "claude_md": claude_md,
                "live_features": json.dumps(live_features, default=str, ensure_ascii=False),
                "known_screens": json.dumps(known_screens, default=str, ensure_ascii=False),
            })

            state_summary = state.get("state_summary", json.dumps(state, default=str))
            gaps = state.get("gaps", [])
            # Include gaps in state_summary so all agents see them
            if gaps:
                gaps_text = "\n\nKnown gaps/issues:\n" + "\n".join(f"- {g}" for g in gaps)
                state_summary = state_summary + gaps_text

            # Update screens catalog
            for screen in state.get("screens", []):
                if isinstance(screen, dict):
                    self.repo.upsert_screen(
                        screen.get("route", ""),
                        screen.get("name", ""),
                        screen.get("description", ""),
                        run_id,
                    )
                elif isinstance(screen, str):
                    self.repo.upsert_screen(screen, screen, "", run_id)

            # === Phase 2: Idea Generation ===
            self._advance_phase(run_id, "IDEA_GENERATION")
            recent_ideas = self.repo.get_recent_ideas(limit=30)

            ideas_result = self.idea_generator.run(run_id, {
                "claude_md": claude_md,
                "state_summary": state_summary,
                "max_idea_size": MAX_IDEA_SIZE,
                "live_features": json.dumps(
                    [f.get("title", "") for f in live_features], ensure_ascii=False
                ),
                "recent_ideas": json.dumps(
                    [{"title": i.get("title"), "rejected": i.get("rejected_reason")}
                     for i in recent_ideas if i.get("rejected_reason")],
                    ensure_ascii=False,
                ),
                "blocklist": "\n".join(f"- {b}" for b in BLOCKLIST),
            })

            ideas = ideas_result.get("ideas", [])
            if len(ideas) < 1:
                raise RunError("Idea generator returned no ideas")

            # Save ideas to DB
            idea_ids = []
            for idea in ideas:
                idea_id = self.repo.save_idea(run_id, idea)
                idea_ids.append(idea_id)

            # === Phase 3: Evaluation ===
            self._advance_phase(run_id, "EVALUATION")

            decision = self.evaluator.run(run_id, {
                "claude_md": claude_md,
                "state_summary": state_summary,
                "max_idea_size": MAX_IDEA_SIZE,
                "ideas_json": json.dumps(ideas, ensure_ascii=False, indent=2),
            })

            chosen_idx = decision.get("chosen", {}).get("idea_index", 0)
            chosen_idx = min(chosen_idx, len(ideas) - 1)
            chosen_idea = ideas[chosen_idx]
            chosen_idea_id = idea_ids[chosen_idx]

            # Log decision
            self.event_bus.emit(
                run_id=run_id, phase="EVALUATION", agent_name="evaluator",
                severity="DECISION", event_type="feature_chosen",
                message=f"Chosen: {chosen_idea.get('title', 'unknown')}",
                data=decision,
            )

            self.repo.save_decision(
                run_id,
                chosen_idea_id,
                decision.get("chosen", {}).get("score", 0),
                decision.get("chosen", {}).get("rationale", ""),
                json.dumps(decision.get("rejected", []), ensure_ascii=False),
            )

            # Reject other ideas
            for rejected in decision.get("rejected", []):
                idx = rejected.get("idea_index", -1)
                if 0 <= idx < len(idea_ids) and idx != chosen_idx:
                    self.repo.reject_idea(idea_ids[idx], rejected.get("reason", "Not selected"))

            self.repo.update_run_feature(run_id, chosen_idea.get("title", "unknown"))

            # === Phase 4: Build ===
            self._advance_phase(run_id, "BUILD")

            self.builder.run(run_id, {
                "feature_title": chosen_idea.get("title", ""),
                "feature_description": chosen_idea.get("description", ""),
                "state_summary": state_summary,
                "claude_md": claude_md,
            })

            # Check if builder actually changed anything
            git_status = self.git.get_status()
            if git_status["clean"]:
                raise RunError("Builder made no changes")

            # === Phase 5: Test ===
            self._advance_phase(run_id, "TEST")

            test_result = self.tester.run(run_id)

            if not test_result["all_passed"]:
                raise TestFailure(test_result)

            # === Phase 6: Pre-commit checks ===
            changed_files = (
                git_status.get("modified", [])
                + git_status.get("added", [])
            )
            ok, msg = run_pre_commit_checks(changed_files)
            if not ok:
                raise RunError(f"Pre-commit check failed: {msg}")

            # === Phase 7: Commit ===
            self._advance_phase(run_id, "COMMIT")

            test_status = "all_passed" if test_result["all_passed"] else "partial"
            commit_hash = self.git.commit(
                run_id=run_id,
                feature_title=chosen_idea.get("title", "unknown"),
                summary=chosen_idea.get("description", ""),
                screen=chosen_idea.get("affected_screen", ""),
                test_status=test_status,
            )

            files_changed = self.git.get_files_changed()
            self.repo.save_git_history(run_id, commit_hash, chosen_idea.get("title", ""), files_changed)

            # === Phase 8: Push ===
            if AUTO_PUSH:
                self._advance_phase(run_id, "PUSH")
                push_ok = self.git.push()
                if not push_ok:
                    logger.warning("Push failed, but commit is local")
                    self.repo.save_failure(
                        run_id, "PUSH", "push_failed", "Git push failed",
                    )

            # === Phase 9: History ===
            self._advance_phase(run_id, "HISTORY")

            run_events = self.repo.get_run_events(run_id)
            tests = self.repo.get_tests_for_run(run_id)

            self.historian.run(run_id, {
                "run_id": run_id,
                "feature_title": chosen_idea.get("title", ""),
                "feature_description": chosen_idea.get("description", ""),
                "run_events": json.dumps(
                    [{"phase": e["phase"], "message": e["message"]} for e in run_events],
                    ensure_ascii=False,
                ),
                "test_results": json.dumps(
                    [{"type": t["test_type"], "passed": bool(t["passed"])} for t in tests],
                    ensure_ascii=False,
                ),
                "files_changed": files_changed,
                "decision_rationale": decision.get("chosen", {}).get("rationale", ""),
            })

            # Mark feature as live
            self.repo.mark_feature_live(
                run_id,
                chosen_idea.get("title", ""),
                chosen_idea.get("description", ""),
                files_changed,
                chosen_idea.get("affected_screen", ""),
                commit_hash,
            )

            # === Complete ===
            duration_ms = int((time.time() - start_time) * 1000)
            self.repo.complete_run(run_id, duration_ms)

            self.event_bus.emit(
                run_id=run_id, phase="COMPLETE", agent_name="orchestrator",
                severity="INFO", event_type="run_complete",
                message=f"Run {run_id} completed: {chosen_idea.get('title', '')}",
                data={"duration_ms": duration_ms, "commit_hash": commit_hash},
            )

            logger.info(
                "Run %s completed in %ds: %s",
                run_id, duration_ms / 1000, chosen_idea.get("title", ""),
            )
            return run_id

        except TestFailure as e:
            return self._handle_failure(run_id, "TEST", "test_failure", str(e), start_time)

        except RunError as e:
            phase = self.repo.get_run(run_id).get("phase", "UNKNOWN") if self.repo.get_run(run_id) else "UNKNOWN"
            return self._handle_failure(run_id, phase, "run_error", str(e), start_time)

        except AgentError as e:
            phase = self.repo.get_run(run_id).get("phase", "UNKNOWN") if self.repo.get_run(run_id) else "UNKNOWN"
            return self._handle_failure(run_id, phase, "agent_error", str(e), start_time)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Unexpected error in run %s: %s\n%s", run_id, e, tb)
            phase = "UNKNOWN"
            try:
                run = self.repo.get_run(run_id)
                if run:
                    phase = run.get("phase", "UNKNOWN")
            except Exception:
                pass
            return self._handle_failure(run_id, phase, "unexpected_error", f"{e}\n{tb}", start_time)

    def _advance_phase(self, run_id: str, phase: str) -> None:
        """Advance the run to a new phase."""
        self.repo.update_run_phase(run_id, phase)
        self.repo.update_run_status(run_id, "RUNNING")
        self.event_bus.emit(
            run_id=run_id, phase=phase, agent_name="orchestrator",
            severity="INFO", event_type="phase_change",
            message=f"Entering phase: {phase}",
        )

    def _handle_failure(self, run_id: str, phase: str, error_type: str,
                        error_message: str, start_time: float) -> str:
        """Handle a run failure with cleanup and logging."""
        duration_ms = int((time.time() - start_time) * 1000)

        logger.error("Run %s failed in %s: %s", run_id, phase, error_message[:500])

        # Save error artifact
        save_error_artifact(run_id, error_message, {"phase": phase, "error_type": error_type})

        # Save failure record
        self.repo.save_failure(run_id, phase, error_type, error_message[:2000])

        # Update run status
        self.repo.update_run_status(run_id, "FAILED", error_message[:500])

        # Cleanup: discard any uncommitted changes
        try:
            if not self.git.check_clean():
                self.git.discard_changes()
                self.repo.save_recovery_action(
                    self.repo.save_failure(run_id, phase, "cleanup", "Discarded uncommitted changes"),
                    "discard_changes", "success",
                )
        except Exception as cleanup_err:
            logger.error("Cleanup failed: %s", cleanup_err)

        self.event_bus.emit(
            run_id=run_id, phase=phase, agent_name="orchestrator",
            severity="ERROR", event_type="run_failed",
            message=f"Run failed: {error_message[:200]}",
            data={"error_type": error_type, "duration_ms": duration_ms},
        )

        return run_id

    def _read_claude_md(self) -> str:
        """Read the CLAUDE.md project constitution."""
        try:
            with open(CLAUDE_MD_PATH, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("CLAUDE.md not found at %s", CLAUDE_MD_PATH)
            return "No CLAUDE.md found. The web application needs a project constitution."

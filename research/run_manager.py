"""Research Run Manager - state machine for research pipeline execution."""

import logging
import time
import uuid
from enum import Enum

from orchestrator.event_bus import EventBus
from db.research_repository import ResearchRepository
from research.config import RESEARCH_DAILY_BUDGET_CAP

logger = logging.getLogger("onjaro.research.run_manager")


class ResearchPhase(str, Enum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    FETCHING = "FETCHING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    NORMALIZING = "NORMALIZING"
    DEDUPING = "DEDUPING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    RETRY_WAIT = "RETRY_WAIT"
    CANCELLED = "CANCELLED"


class ResearchRunManager:
    """Manages the lifecycle of a research run through its pipeline phases."""

    def __init__(self, repo: ResearchRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus
        # Pipeline components will be injected as they are built in later phases
        self._config_loader = None
        self._fetcher = None
        self._extractor = None
        self._validator = None
        self._normalizer = None
        self._deduplicator = None
        self._persister = None

    def set_config_loader(self, config_loader):
        self._config_loader = config_loader

    def set_pipeline_components(self, fetcher=None, extractor=None,
                                validator=None, normalizer=None,
                                deduplicator=None, persister=None):
        if fetcher:
            self._fetcher = fetcher
        if extractor:
            self._extractor = extractor
        if validator:
            self._validator = validator
        if normalizer:
            self._normalizer = normalizer
        if deduplicator:
            self._deduplicator = deduplicator
        if persister:
            self._persister = persister

    def execute_research_run(self, trigger_type: str = "scheduled") -> str:
        """Execute a full research run. Returns run_id or None if skipped."""
        # Budget check
        daily_cost = self.repo.get_daily_research_cost()
        if daily_cost >= RESEARCH_DAILY_BUDGET_CAP:
            logger.warning("Research daily budget cap reached ($%.2f >= $%.2f), skipping",
                           daily_cost, RESEARCH_DAILY_BUDGET_CAP)
            return None

        run_id = f"res_{uuid.uuid4().hex[:10]}"
        start_time = time.time()

        logger.info("Starting research run: %s", run_id)
        self.repo.create_research_run(run_id, trigger_type=trigger_type)

        self.event_bus.emit(
            run_id=run_id, phase=ResearchPhase.QUEUED, agent_name="research_manager",
            severity="INFO", event_type="research_run_start",
            message=f"Research run {run_id} started ({trigger_type})",
        )

        try:
            self._execute_pipeline(run_id)

            duration_ms = int((time.time() - start_time) * 1000)
            self.repo.complete_research_run(run_id, status="COMPLETED", duration_ms=duration_ms)

            self.event_bus.emit(
                run_id=run_id, phase=ResearchPhase.COMPLETED, agent_name="research_manager",
                severity="INFO", event_type="research_run_complete",
                message=f"Research run {run_id} completed in {duration_ms}ms",
                data={"duration_ms": duration_ms},
            )

            logger.info("Research run %s completed in %dms", run_id, duration_ms)
            return run_id

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.error("Research run %s failed: %s", run_id, error_msg)

            self.repo.update_research_status(run_id, "FAILED", error_message=error_msg)
            self.repo.complete_research_run(run_id, status="FAILED", duration_ms=duration_ms)

            self.event_bus.emit(
                run_id=run_id, phase=ResearchPhase.FAILED, agent_name="research_manager",
                severity="ERROR", event_type="research_run_failed",
                message=f"Research run failed: {error_msg}",
            )
            return run_id

    def _execute_pipeline(self, run_id: str):
        """Run the full research pipeline for all configured research items."""
        # Load project config
        if not self._config_loader:
            logger.warning("No config loader set, cannot load research items")
            self._advance_phase(run_id, ResearchPhase.COMPLETED)
            return

        self._advance_phase(run_id, ResearchPhase.PLANNING)

        items = self._config_loader.load_items()
        if not items:
            logger.info("No research items configured, nothing to do")
            return

        self.repo.update_research_items_count(run_id, total=len(items))
        logger.info("Loaded %d research items", len(items))

        completed = 0
        failed = 0

        for item in items:
            if not item.get("enabled", True):
                logger.info("Skipping disabled item: %s", item.get("id", "?"))
                continue

            try:
                self._process_item(run_id, item)
                completed += 1
                self.repo.update_research_items_count(run_id, completed=completed)
            except Exception as e:
                failed += 1
                self.repo.update_research_items_count(run_id, failed=failed)
                logger.error("Research item '%s' failed: %s", item.get("id", "?"), e)

                self.event_bus.emit(
                    run_id=run_id, phase=self.repo.get_research_run(run_id).get("phase", ""),
                    agent_name="research_manager", severity="ERROR",
                    event_type="research_item_failed",
                    message=f"Item '{item.get('id', '?')}' failed: {e}",
                )

        if failed > 0 and completed > 0:
            self.repo.update_research_status(run_id, "PARTIAL_SUCCESS")
        elif failed > 0 and completed == 0:
            raise RuntimeError(f"All {failed} research items failed")

        # ── Deep Crawl Phase: mine known companies for people & buildings ──
        try:
            self._execute_deep_crawl(run_id)
        except Exception as e:
            logger.error("Deep crawl phase failed (non-fatal): %s", e)

    def _process_item(self, run_id: str, item: dict):
        """Process a single research item through all pipeline phases."""
        item_id = item.get("id", "unknown")
        logger.info("Processing research item: %s (%s)", item_id, item.get("name", ""))

        self.repo.create_research_item_log(run_id, item_id)

        # Phase: FETCHING
        self._advance_phase(run_id, ResearchPhase.FETCHING)
        self.repo.update_research_item_log(run_id, item_id, phase="FETCHING")

        raw_findings = []
        if self._fetcher:
            raw_findings = self._fetcher.fetch_for_item(run_id, item)
            self.repo.update_research_item_log(
                run_id, item_id, raw_findings_count=len(raw_findings)
            )
            logger.info("Item %s: %d raw findings", item_id, len(raw_findings))
        else:
            logger.warning("No fetcher configured, skipping fetch phase")

        if not raw_findings:
            self.repo.update_research_item_log(run_id, item_id, status="completed",
                                               phase="COMPLETED")
            return

        # Phase: EXTRACTING
        self._advance_phase(run_id, ResearchPhase.EXTRACTING)
        self.repo.update_research_item_log(run_id, item_id, phase="EXTRACTING")

        candidates = []
        if self._extractor:
            candidates = self._extractor.extract_from_findings(run_id, item, raw_findings)
            self.repo.update_research_item_log(
                run_id, item_id, extracted_count=len(candidates)
            )
            logger.info("Item %s: %d extraction candidates", item_id, len(candidates))

        if not candidates:
            self.repo.update_research_item_log(run_id, item_id, status="completed",
                                               phase="COMPLETED")
            return

        # Phase: VALIDATING
        self._advance_phase(run_id, ResearchPhase.VALIDATING)
        self.repo.update_research_item_log(run_id, item_id, phase="VALIDATING")

        validated = candidates
        if self._validator:
            validated = self._validator.validate_candidates(run_id, item, candidates)
            self.repo.update_research_item_log(
                run_id, item_id, validated_count=len(validated)
            )

        # Phase: NORMALIZING
        self._advance_phase(run_id, ResearchPhase.NORMALIZING)
        self.repo.update_research_item_log(run_id, item_id, phase="NORMALIZING")

        normalized = validated
        if self._normalizer:
            normalized = self._normalizer.normalize(run_id, item, validated)

        # Phase: DEDUPING
        self._advance_phase(run_id, ResearchPhase.DEDUPING)
        self.repo.update_research_item_log(run_id, item_id, phase="DEDUPING")

        to_persist = normalized
        skipped = 0
        if self._deduplicator:
            to_persist, skipped = self._deduplicator.dedupe(run_id, item, normalized)
            self.repo.update_research_item_log(run_id, item_id, skipped_count=skipped)

        # Phase: PERSISTING
        self._advance_phase(run_id, ResearchPhase.PERSISTING)
        self.repo.update_research_item_log(run_id, item_id, phase="PERSISTING")

        persisted = 0
        if self._persister and to_persist:
            persisted = self._persister.persist(run_id, item, to_persist)
            self.repo.update_research_item_log(run_id, item_id, persisted_count=persisted)

        self.repo.update_research_item_log(run_id, item_id, status="completed",
                                           phase="COMPLETED")

        self.event_bus.emit(
            run_id=run_id, phase=ResearchPhase.PERSISTING, agent_name="research_manager",
            severity="INFO", event_type="research_item_complete",
            message=f"Item '{item_id}': {persisted} persisted, {skipped} skipped",
            data={"item_id": item_id, "raw": len(raw_findings),
                  "extracted": len(candidates), "persisted": persisted, "skipped": skipped},
        )

    def _advance_phase(self, run_id: str, phase: ResearchPhase):
        """Update the current phase and emit event."""
        self.repo.update_research_phase(run_id, phase.value)
        self.event_bus.emit(
            run_id=run_id, phase=phase.value, agent_name="research_manager",
            severity="INFO", event_type="research_phase_change",
            message=f"Research phase: {phase.value}",
        )

    def _execute_deep_crawl(self, run_id: str):
        """Deep crawl: search known companies for their people and buildings.

        Picks companies that haven't been deeply crawled yet (or not recently),
        generates dynamic search items for them, and processes them through the
        standard pipeline.
        """
        from research.pipeline.deep_crawl import (
            get_companies_to_crawl,
            generate_deep_crawl_items,
            mark_company_crawled,
        )

        companies = get_companies_to_crawl()
        if not companies:
            logger.info("Deep crawl: no companies eligible for deep crawl")
            return

        company_names = [c.get("name", "?") for c in companies]
        logger.info("Deep crawl: processing %d companies: %s",
                     len(companies), ", ".join(company_names))

        self.event_bus.emit(
            run_id=run_id, phase="DEEP_CRAWL", agent_name="research_manager",
            severity="INFO", event_type="research_phase_change",
            message=f"Deep crawl: {len(companies)} cég feldolgozása ({', '.join(company_names[:3])})",
        )

        deep_items = generate_deep_crawl_items(companies)
        crawled_company_ids = set()

        for item in deep_items:
            try:
                if item.get("_deep_crawl_enrich"):
                    # Company enrichment: run extraction then merge into existing record
                    self._enrich_company(run_id, item)
                else:
                    self._process_item(run_id, item)
                # Mark company as crawled after all items are done
                company_id = item.get("_deep_crawl_company_id", "")
                if company_id:
                    crawled_company_ids.add(company_id)
            except Exception as e:
                logger.error("Deep crawl item '%s' failed: %s", item.get("id", "?"), e)

        # Mark all processed companies as crawled
        for cid in crawled_company_ids:
            mark_company_crawled(cid)
            logger.info("Deep crawl: marked company %s as crawled", cid[:12])

        logger.info("Deep crawl: completed for %d companies", len(crawled_company_ids))

    def _enrich_company(self, run_id: str, item: dict):
        """Enrich a skeleton company record with research data.

        Runs fetch+extract, then merges the best result into the existing
        company record (updates only empty/default fields).
        """
        company_id = item.get("_deep_crawl_company_id", "")
        company_name = item.get("_deep_crawl_company_name", "")
        item_id = item.get("id", "unknown")

        logger.info("Company enrichment: researching '%s' (%s)", company_name, company_id[:12])

        # Fetch raw findings
        self.repo.create_research_item_log(run_id, item_id)
        self.repo.update_research_item_log(run_id, item_id, status="running", phase="FETCHING")

        raw_findings = self._fetcher.fetch(run_id, item)
        if not raw_findings:
            logger.info("Company enrichment: no findings for '%s'", company_name)
            self.repo.update_research_item_log(run_id, item_id, status="completed", phase="COMPLETED")
            return

        # Extract structured data
        self.repo.update_research_item_log(run_id, item_id, phase="EXTRACTING")
        candidates = self._extractor.extract_from_findings(run_id, item, raw_findings)
        if not candidates:
            logger.info("Company enrichment: no candidates for '%s'", company_name)
            self.repo.update_research_item_log(run_id, item_id, status="completed", phase="COMPLETED")
            return

        # Validate
        if self._validator:
            candidates = self._validator.validate_candidates(run_id, item, candidates)

        # Normalize
        if self._normalizer:
            candidates = self._normalizer.normalize(run_id, item, candidates)

        if not candidates:
            self.repo.update_research_item_log(run_id, item_id, status="completed", phase="COMPLETED")
            return

        # Pick the best candidate (highest confidence)
        best = max(candidates, key=lambda c: c.confidence)
        data = best.extracted_data

        # Build update dict: only fill in fields that are currently empty in DB
        from research.supabase_client import get_supabase_client
        client = get_supabase_client()
        if not client:
            return

        try:
            existing = client.table("companies").select("*").eq("id", company_id).execute()
            if not existing.data:
                return
            record = existing.data[0]
        except Exception as e:
            logger.error("Company enrichment: failed to fetch existing record: %s", e)
            return

        updates = {}
        # Map of normalized fields to check and potentially update
        _ENRICHABLE_FIELDS = {
            "description": ("description", lambda v: bool(v and len(str(v)) > 10)),
            "service_types": ("service_types", lambda v: bool(v and isinstance(v, list) and len(v) > 0)),
            "website": ("website", lambda v: bool(v)),
            "headquarters_city": ("headquarters_city", lambda v: bool(v)),
            "headquarters_address": ("headquarters_address", lambda v: bool(v)),
            "founded_year": ("founded_year", lambda v: bool(v)),
            "employee_count_estimate": ("employee_count_estimate", lambda v: bool(v)),
            "is_international": ("is_international", lambda v: v is True),
            "name_aliases": ("name_aliases", lambda v: bool(v and isinstance(v, list) and len(v) > 0)),
        }

        for field, (db_col, has_value) in _ENRICHABLE_FIELDS.items():
            existing_val = record.get(db_col)
            new_val = data.get(field)
            # Only update if existing is empty/default and new has real value
            if not has_value(existing_val) and has_value(new_val):
                updates[db_col] = new_val

        # Also process key_people if present
        key_people = data.get("_key_people") or []

        if updates:
            from datetime import datetime, timezone
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            updates["last_confirmed_at"] = updates["updated_at"]
            # Boost confidence since we now have real data
            if (record.get("confidence") or 0) < 0.5:
                updates["confidence"] = 0.5

            try:
                client.table("companies").update(updates).eq("id", company_id).execute()
                logger.info(
                    "Company enrichment: updated '%s' with %d fields: %s",
                    company_name, len(updates) - 2,  # exclude timestamps
                    ", ".join(k for k in updates if k not in ("updated_at", "last_confirmed_at", "confidence")),
                )
            except Exception as e:
                logger.error("Company enrichment: update failed for '%s': %s", company_name, e)

            # Process key_people through the persister's related entities logic
            if key_people and self._persister:
                from research.pipeline.persister import ResearchPersister
                mappings = self._config_loader.load_mappings() if self._config_loader else {}
                company_config = mappings.get("companies", {})
                related_cfg = company_config.get("related_entities", {}).get("key_people", {})
                if related_cfg:
                    self._persister._process_related_entities(
                        client, company_id, "companies",
                        key_people, related_cfg, {"source_urls": []},
                    )

        self.repo.update_candidate_status(best.candidate_id, "persisted")
        self.repo.update_research_item_log(run_id, item_id, status="completed", phase="COMPLETED",
                                           persisted_count=1 if updates else 0)
        logger.info("Company enrichment: done for '%s'", company_name)

    def execute_single_item(self, item_id: str, trigger_type: str = "manual") -> str:
        """Run research for a single item (ad-hoc run)."""
        if not self._config_loader:
            logger.error("No config loader set")
            return None

        items = self._config_loader.load_items()
        target = next((i for i in items if i.get("id") == item_id), None)
        if not target:
            logger.error("Research item '%s' not found", item_id)
            return None

        run_id = f"res_{uuid.uuid4().hex[:10]}"
        start_time = time.time()

        self.repo.create_research_run(run_id, trigger_type=trigger_type)
        self.repo.update_research_items_count(run_id, total=1)

        self.event_bus.emit(
            run_id=run_id, phase=ResearchPhase.QUEUED, agent_name="research_manager",
            severity="INFO", event_type="research_run_start",
            message=f"Ad-hoc research run for '{item_id}'",
        )

        try:
            self._process_item(run_id, target)
            duration_ms = int((time.time() - start_time) * 1000)
            self.repo.complete_research_run(run_id, status="COMPLETED", duration_ms=duration_ms)
            self.repo.update_research_items_count(run_id, completed=1)
            return run_id
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.repo.complete_research_run(run_id, status="FAILED", duration_ms=duration_ms)
            self.repo.update_research_status(run_id, "FAILED", error_message=str(e))
            logger.error("Ad-hoc research run failed: %s", e)
            return run_id

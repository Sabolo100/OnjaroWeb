"""Research Persister - writes validated records to Supabase."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate
from research.supabase_client import get_supabase_client
from research.pipeline.deduplicator import normalize_company_name
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.persister")


class ResearchPersister:
    """Persists validated and deduplicated records to Supabase."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()

    def persist(self, run_id: str, item: dict,
                candidates: List[ExtractionCandidate]) -> int:
        """Persist candidates to Supabase.

        Returns the number of successfully persisted records.
        """
        target_table = item.get("target_table", "articles")
        policies = self.config.load_policies()
        mappings = self.config.load_mappings()
        table_config = mappings.get(target_table, {})
        required_fields = table_config.get("required_fields", [])
        field_mapping = table_config.get("field_mapping", {})
        defaults = table_config.get("defaults", {})
        auto_fields = table_config.get("auto_fields", {})
        resolve_fields = table_config.get("resolve_fields", {})
        related_entities = table_config.get("related_entities", {})

        # Build whitelist of allowed DB columns from persistence config.
        # Exclude _-prefixed sentinels (internal markers) from the whitelist.
        allowed_columns = (
            set(v for v in field_mapping.values() if not v.startswith("_"))
            | set(defaults.keys())
            | set(auto_fields.keys())
        )
        # Also allow the resolved FK columns (e.g. current_company_id)
        for col_name in resolve_fields:
            allowed_columns.add(col_name)

        client = get_supabase_client()
        if not client:
            logger.error("No Supabase client available, cannot persist")
            return 0

        persisted = 0

        for candidate in candidates:
            try:
                data = candidate.extracted_data.copy()

                # Check for update vs insert
                existing_id = data.pop("_update_existing_id", None)

                # NOTE: field_mapping (title->name, current_company_name->_resolve_company, etc.)
                # is already applied by the normalizer. The data arriving here has DB column
                # names and _-prefixed sentinel keys. Do NOT re-apply field_mapping.

                # --- Resolve FK fields before column filtering ---
                # e.g. _resolve_company -> current_company_id for people
                if resolve_fields:
                    self._resolve_foreign_keys(client, data, resolve_fields)

                # --- Extract related entities data before column filtering ---
                # e.g. _key_people for companies -> will create person+job later
                related_data = {}
                for rel_name, rel_cfg in related_entities.items():
                    source_field = rel_cfg.get("source_field", "")
                    related_data[rel_name] = data.pop(source_field, None)

                # Filter to only allowed columns
                if allowed_columns:
                    filtered = {k: v for k, v in data.items() if k in allowed_columns}
                else:
                    filtered = data

                # Verify required fields
                missing = [f for f in required_fields if not filtered.get(f)]
                if missing:
                    self.repo.save_persistence_result(
                        run_id, candidate.candidate_id, "rejected",
                        target_table=target_table,
                        reason=f"Missing required fields: {missing}",
                    )
                    self.repo.update_candidate_status(
                        candidate.candidate_id, "rejected",
                        f"Missing required fields: {missing}"
                    )
                    continue

                if existing_id:
                    # For updates: only overwrite FK fields (like current_company_id)
                    # if they are currently NULL in the DB. Never overwrite an existing
                    # company link with a different one from a later extraction.
                    update_data = filtered.copy()
                    if target_table == "people" and "current_company_id" in update_data:
                        try:
                            existing_resp = client.table(target_table).select(
                                "current_company_id"
                            ).eq("id", existing_id).execute()
                            if existing_resp.data and existing_resp.data[0].get("current_company_id"):
                                # Already has a company — don't overwrite, but still create job
                                update_data.pop("current_company_id", None)
                        except Exception:
                            pass
                    result = self._update_record(client, target_table, existing_id, update_data)
                    action = "updated"
                else:
                    result = self._insert_record(client, target_table, filtered)
                    action = "inserted"

                if result:
                    target_id = result.get("id", "")
                    self.repo.save_persistence_result(
                        run_id, candidate.candidate_id, action,
                        target_table=target_table, target_id=str(target_id),
                    )
                    self.repo.update_candidate_status(candidate.candidate_id, "persisted")

                    persisted += 1
                    record_name = filtered.get("name", filtered.get("title", ""))
                    logger.info("Persisted record to '%s': %s (%s)",
                                target_table, str(record_name)[:50], action)

                    # --- Create job record for person -> company link ---
                    if (target_table == "people"
                            and target_id
                            and filtered.get("current_company_id")):
                        position_title = filtered.get("title", "Nem ismert")
                        self._find_or_create_job(
                            client,
                            jobs_table="jobs",
                            person_id=str(target_id),
                            company_id=filtered["current_company_id"],
                            position_title=position_title,
                            position_category=data.get("position_category"),
                            defaults={"is_current": True, "confidence": candidate.confidence},
                            source_urls=filtered.get("source_urls", []),
                            now_iso=datetime.now(timezone.utc).isoformat(),
                        )

                    # --- Process related entities (e.g. key_people) ---
                    if target_id:
                        for rel_name, rel_cfg in related_entities.items():
                            rel_items = related_data.get(rel_name)
                            if rel_items:
                                self._process_related_entities(
                                    client, str(target_id), target_table,
                                    rel_items, rel_cfg, filtered
                                )
                else:
                    self.repo.save_persistence_result(
                        run_id, candidate.candidate_id, "rejected",
                        target_table=target_table,
                        reason="Supabase write returned no result",
                    )

            except Exception as e:
                logger.error("Failed to persist candidate %d: %s",
                             candidate.candidate_id, e)
                self.repo.save_persistence_result(
                    run_id, candidate.candidate_id, "rejected",
                    target_table=target_table, reason=str(e),
                )

        logger.info("Persisted %d/%d records to '%s'",
                    persisted, len(candidates), target_table)
        return persisted

    # ------------------------------------------------------------------ #
    #  Related entities: key_people -> person + job records               #
    # ------------------------------------------------------------------ #

    def _process_related_entities(
        self,
        client,
        parent_id: str,
        parent_table: str,
        items: list,
        config: dict,
        parent_data: dict,
    ):
        """Process related entities extracted alongside the parent record.

        Currently handles key_people: creates/finds person records and links
        them to the parent company via the jobs table.
        """
        if not isinstance(items, list) or not items:
            return

        person_table = config.get("person_table", "people")
        jobs_table = config.get("jobs_table", "jobs")
        person_defaults = config.get("person_defaults", {})
        job_defaults = config.get("job_defaults", {})
        source_urls = parent_data.get("source_urls", [])

        now_iso = datetime.now(timezone.utc).isoformat()

        for person_entry in items:
            # Support both dict and Pydantic model-like objects
            if hasattr(person_entry, "dict"):
                person_entry = person_entry.dict()
            if not isinstance(person_entry, dict):
                continue

            person_name = (person_entry.get("name") or "").strip()
            if not person_name or len(person_name) < 2:
                continue

            position_title = person_entry.get("position_title")
            position_category = person_entry.get("position_category")

            try:
                # 1) Find or create person
                person_id = self._find_or_create_person(
                    client,
                    person_table=person_table,
                    name=person_name,
                    company_id=parent_id,
                    position_title=position_title,
                    defaults=person_defaults,
                    source_urls=source_urls,
                    now_iso=now_iso,
                )
                if not person_id:
                    continue

                # 2) Find or create a current job linking person → company
                self._find_or_create_job(
                    client,
                    jobs_table=jobs_table,
                    person_id=person_id,
                    company_id=parent_id,
                    position_title=position_title,
                    position_category=position_category,
                    defaults=job_defaults,
                    source_urls=source_urls,
                    now_iso=now_iso,
                )

                logger.info(
                    "Linked person '%s' (%s) to company id=%s",
                    person_name,
                    position_title or "unknown role",
                    parent_id[:8],
                )

            except Exception as e:
                logger.error(
                    "Failed to create related person '%s': %s",
                    person_name, e
                )

    def _find_or_create_person(
        self,
        client,
        person_table: str,
        name: str,
        company_id: str,
        position_title: Optional[str],
        defaults: dict,
        source_urls: list,
        now_iso: str,
    ) -> Optional[str]:
        """Find an existing person by name or create a new one.

        Uses case-insensitive comparison.  When found, updates
        current_company_id and title if they are currently empty.
        """
        name_lower = name.strip().lower()

        try:
            # Fetch all people names for soft matching
            resp = client.table(person_table).select("id,name,current_company_id,title").execute()
            existing = resp.data or []

            for record in existing:
                existing_name = (record.get("name") or "").strip().lower()
                if existing_name == name_lower:
                    person_id = record["id"]
                    # Update company/title if currently empty
                    updates = {}
                    if not record.get("current_company_id"):
                        updates["current_company_id"] = company_id
                    if not record.get("title") and position_title:
                        updates["title"] = position_title
                    if updates:
                        updates["updated_at"] = now_iso
                        updates["last_confirmed_at"] = now_iso
                        client.table(person_table).update(updates).eq("id", person_id).execute()
                        logger.debug("Updated existing person '%s' with company link", name)
                    return person_id

            # Not found — create new person
            new_person = {
                "name": name,
                "current_company_id": company_id,
                "title": position_title,
                "source_urls": source_urls if isinstance(source_urls, list) else [],
                "created_at": now_iso,
                "updated_at": now_iso,
                "first_seen_at": now_iso,
                "last_confirmed_at": now_iso,
                **defaults,
            }
            # Remove None values to let DB defaults handle them
            new_person = {k: v for k, v in new_person.items() if v is not None}

            insert_resp = client.table(person_table).insert(new_person).execute()
            if insert_resp.data:
                new_id = insert_resp.data[0]["id"]
                logger.info(
                    "Created new person from company key_people: '%s' (id=%s)",
                    name, new_id
                )
                return new_id

        except Exception as e:
            logger.error("Error finding/creating person '%s': %s", name, e)

        return None

    def _find_or_create_job(
        self,
        client,
        jobs_table: str,
        person_id: str,
        company_id: str,
        position_title: Optional[str],
        position_category: Optional[str],
        defaults: dict,
        source_urls: list,
        now_iso: str,
    ):
        """Find or create a current job linking person to company.

        Checks if a current (ended_at IS NULL) job already exists for
        this person at this company.  If so, updates title if missing.
        Otherwise creates a new job with started_at = NULL (unknown start),
        ended_at = NULL (currently active).
        """
        try:
            # Check for existing current job at this company
            resp = (
                client.table(jobs_table)
                .select("id,position_title,position_category")
                .eq("person_id", person_id)
                .eq("company_id", company_id)
                .is_("ended_at", "null")
                .execute()
            )
            existing_jobs = resp.data or []

            if existing_jobs:
                # Already has a current job here — update if we have new info
                job = existing_jobs[0]
                updates = {}
                if not job.get("position_title") and position_title:
                    updates["position_title"] = position_title
                if not job.get("position_category") and position_category:
                    updates["position_category"] = position_category
                if updates:
                    updates["updated_at"] = now_iso
                    client.table(jobs_table).update(updates).eq("id", job["id"]).execute()
                    logger.debug("Updated existing job for person %s at company %s", person_id[:8], company_id[:8])
                return

            # Create new current job
            new_job = {
                "person_id": person_id,
                "company_id": company_id,
                "position_title": position_title or "Nem ismert",
                "position_category": position_category,
                "started_at": None,      # Unknown when they started
                "ended_at": None,         # Currently active
                "source_urls": source_urls if isinstance(source_urls, list) else [],
                "created_at": now_iso,
                "updated_at": now_iso,
                **defaults,
            }
            new_job = {k: v for k, v in new_job.items() if v is not None}

            client.table(jobs_table).insert(new_job).execute()
            logger.info(
                "Created new job: person %s at company %s as '%s'",
                person_id[:8], company_id[:8], position_title or "unknown"
            )

        except Exception as e:
            logger.error(
                "Error creating job for person %s at company %s: %s",
                person_id[:8], company_id[:8], e
            )

    # ------------------------------------------------------------------ #
    #  FK resolution (e.g. current_company_name -> current_company_id)   #
    # ------------------------------------------------------------------ #

    def _resolve_foreign_keys(self, client, data: dict, resolve_fields: dict):
        """Resolve fields like current_company_name -> current_company_id.

        For each entry in resolve_fields config:
          - reads the source_field value from data
          - looks up the lookup_table for a matching record
          - if not found and create_if_missing=True, creates a minimal record
          - injects the resolved ID into data as the target FK column
          - removes the sentinel _resolve_company key
        """
        for fk_column, cfg in resolve_fields.items():
            source_field = cfg.get("source_field", "")
            source_value = data.pop(source_field, None)

            if not source_value:
                continue

            lookup_table = cfg.get("lookup_table", "companies")
            lookup_column = cfg.get("lookup_column", "name")
            create_if_missing = cfg.get("create_if_missing", False)
            create_defaults = cfg.get("create_defaults", {})

            company_id = self._find_or_create_entity(
                client,
                table=lookup_table,
                lookup_column=lookup_column,
                lookup_value=str(source_value),
                create_if_missing=create_if_missing,
                create_defaults=create_defaults,
            )

            if company_id:
                data[fk_column] = company_id
                logger.info(
                    "Resolved '%s' = '%s' -> %s=%s",
                    source_field, source_value, fk_column, company_id
                )
            else:
                logger.warning(
                    "Could not resolve '%s' = '%s' to %s",
                    source_field, source_value, fk_column
                )

    def _find_or_create_entity(
        self,
        client,
        table: str,
        lookup_column: str,
        lookup_value: str,
        create_if_missing: bool,
        create_defaults: dict,
    ) -> Optional[str]:
        """Find entity by name (with normalization) or create it if missing."""

        # Normalize for comparison (strips legal forms, activity words)
        norm_value = normalize_company_name(lookup_value)
        if not norm_value:
            return None

        try:
            # Fetch all names for soft matching
            response = client.table(table).select(f"id,{lookup_column}").execute()
            existing = response.data or []

            for record in existing:
                existing_name = str(record.get(lookup_column, ""))
                norm_existing = normalize_company_name(existing_name)
                if norm_existing == norm_value:
                    logger.debug(
                        "Found existing %s: '%s' (id=%s)",
                        table, existing_name, record["id"]
                    )
                    return record["id"]

            # Not found — create if configured
            if create_if_missing:
                new_record = {
                    lookup_column: lookup_value,
                    **create_defaults,
                }
                insert_resp = client.table(table).insert(new_record).execute()
                if insert_resp.data:
                    new_id = insert_resp.data[0]["id"]
                    logger.info(
                        "Created new %s from person link: '%s' (id=%s)",
                        table, lookup_value, new_id
                    )
                    return new_id

        except Exception as e:
            logger.error(
                "Error resolving %s '%s' in %s: %s",
                lookup_column, lookup_value, table, e
            )

        return None

    # ------------------------------------------------------------------ #
    #  Basic CRUD helpers                                                 #
    # ------------------------------------------------------------------ #

    def _insert_record(self, client, table: str, data: dict) -> dict:
        """Insert a new record into Supabase."""
        try:
            response = client.table(table).insert(data).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return {}
        except Exception as e:
            logger.error("Supabase insert failed on '%s': %s", table, e)
            raise

    def _update_record(self, client, table: str,
                       record_id: str, data: dict) -> dict:
        """Update an existing record in Supabase."""
        try:
            response = (
                client.table(table)
                .update(data)
                .eq("id", record_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
            return {}
        except Exception as e:
            logger.error("Supabase update failed on '%s' id=%s: %s",
                         table, record_id, e)
            raise

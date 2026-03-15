"""Research Persister - writes validated records to Supabase."""

import logging
from typing import List

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate
from research.supabase_client import get_supabase_client
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

                # Verify required fields
                missing = [f for f in required_fields if not data.get(f)]
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
                    # Update existing record
                    result = self._update_record(client, target_table, existing_id, data)
                    action = "updated"
                else:
                    # Insert new record
                    result = self._insert_record(client, target_table, data)
                    action = "inserted"

                if result:
                    target_id = result.get("id", "")
                    self.repo.save_persistence_result(
                        run_id, candidate.candidate_id, action,
                        target_table=target_table, target_id=str(target_id),
                    )
                    self.repo.update_candidate_status(candidate.candidate_id, "persisted")

                    # Update source registry on success
                    persisted += 1
                    logger.info("Persisted record to '%s': %s (%s)",
                                target_table, data.get("title", "")[:50], action)
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

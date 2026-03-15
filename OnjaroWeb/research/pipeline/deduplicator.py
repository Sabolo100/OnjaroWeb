"""Research Deduplicator - detect duplicates and changes."""

import logging
from difflib import SequenceMatcher
from typing import List, Tuple

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate
from research.supabase_client import get_supabase_client
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.deduplicator")


class ResearchDeduplicator:
    """Checks extracted candidates against existing records for duplicates."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()

    def dedupe(self, run_id: str, item: dict,
               candidates: List[ExtractionCandidate]) -> Tuple[List[ExtractionCandidate], int]:
        """Check candidates for duplicates.

        Returns:
            (to_persist, skipped_count) - candidates to persist and number skipped
        """
        target_table = item.get("target_table", "articles")
        policies = self.config.load_policies()
        dedupe_policy = policies.dedupe

        # Fetch existing records from Supabase
        existing = self._fetch_existing(target_table, dedupe_policy.unique_keys)

        to_persist = []
        skipped = 0

        for candidate in candidates:
            action, reason = self._check_candidate(
                candidate, existing, dedupe_policy
            )

            if action == "new":
                to_persist.append(candidate)
            elif action == "duplicate":
                skipped += 1
                self.repo.update_candidate_status(
                    candidate.candidate_id, "skipped", reason
                )
                self.repo.save_persistence_result(
                    run_id, candidate.candidate_id, "skipped",
                    target_table=target_table, reason=reason,
                )
                logger.debug("Skipped duplicate: %s", reason)
            elif action == "update_candidate":
                to_persist.append(candidate)
                candidate.extracted_data["_update_existing_id"] = reason
            elif action == "ambiguous":
                # Send to review queue
                self.repo.add_to_review(
                    run_id, candidate.candidate_id,
                    candidate.confidence, f"Ambiguous duplicate: {reason}"
                )
                self.repo.update_candidate_status(
                    candidate.candidate_id, "needs_review", reason
                )
                skipped += 1

        logger.info("Dedupe: %d to persist, %d skipped out of %d candidates",
                    len(to_persist), skipped, len(candidates))
        return to_persist, skipped

    def _fetch_existing(self, table: str, keys: list) -> list:
        """Fetch existing records from Supabase for deduplication."""
        client = get_supabase_client()
        if not client:
            logger.warning("No Supabase client, skipping dedupe against existing records")
            return []

        try:
            # Fetch only the fields we need for comparison
            select_fields = ",".join(["id"] + keys)
            response = client.table(table).select(select_fields).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error("Failed to fetch existing records from '%s': %s", table, e)
            return []

    def _check_candidate(self, candidate: ExtractionCandidate,
                         existing: list, policy) -> Tuple[str, str]:
        """Check a single candidate against existing records.

        Returns: (action, reason)
            action: "new", "duplicate", "update_candidate", "ambiguous"
        """
        data = candidate.extracted_data
        threshold = policy.similarity_threshold
        unique_keys = policy.unique_keys

        if not existing:
            return "new", ""

        for record in existing:
            # Exact key match
            exact_match = all(
                str(data.get(key, "")).lower() == str(record.get(key, "")).lower()
                for key in unique_keys
                if key in data and key in record
            )
            if exact_match:
                return "duplicate", f"Exact match on {unique_keys} with id={record.get('id')}"

            # Soft match (title similarity)
            if "title" in data and "title" in record:
                similarity = SequenceMatcher(
                    None,
                    data["title"].lower(),
                    record["title"].lower(),
                ).ratio()

                if similarity >= threshold:
                    return "duplicate", (
                        f"Title similarity {similarity:.2f} >= {threshold} "
                        f"with '{record['title'][:50]}'"
                    )
                elif similarity >= threshold * 0.85:
                    return "ambiguous", (
                        f"Title similarity {similarity:.2f} near threshold "
                        f"with '{record['title'][:50]}'"
                    )

        return "new", ""

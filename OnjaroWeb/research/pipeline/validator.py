"""Research Validator - schema validation and business rules."""

import logging
from typing import List, Tuple

from pydantic import ValidationError

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.validator")


class ResearchValidator:
    """Validates extraction candidates against schema and business rules."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()

    def validate_candidates(self, run_id: str, item: dict,
                            candidates: List[ExtractionCandidate]) -> List[ExtractionCandidate]:
        """Validate candidates, keeping only valid ones.

        Invalid candidates are marked as 'rejected' in the DB.
        """
        item_id = item.get("id", "unknown")
        schema_name = item.get("schema_name", "article")
        min_confidence = item.get("min_confidence", 0.6)

        schema_cls = self.config.load_schema(schema_name)
        policies = self.config.load_policies()

        valid = []
        rejected = 0

        for candidate in candidates:
            if candidate.status == "rejected":
                rejected += 1
                continue

            rejection_reason = self._validate_single(
                candidate, schema_cls, min_confidence, policies
            )

            if rejection_reason:
                self.repo.update_candidate_status(
                    candidate.candidate_id, "rejected", rejection_reason
                )
                rejected += 1
                logger.debug("Rejected candidate %d: %s",
                             candidate.candidate_id, rejection_reason)
            else:
                self.repo.update_candidate_status(candidate.candidate_id, "validated")
                candidate.status = "validated"
                valid.append(candidate)

        logger.info("Item '%s': %d valid, %d rejected out of %d candidates",
                    item_id, len(valid), rejected, len(candidates))
        return valid

    def _validate_single(self, candidate: ExtractionCandidate,
                         schema_cls, min_confidence: float,
                         policies) -> str:
        """Validate a single candidate. Returns rejection reason or None."""
        data = candidate.extracted_data

        # 1. Confidence check
        if candidate.confidence < min_confidence:
            return f"Confidence too low: {candidate.confidence:.2f} < {min_confidence}"

        # 2. Schema validation (if schema available)
        if schema_cls:
            try:
                schema_cls(**data)
            except ValidationError as ve:
                errors = ve.error_count()
                # Allow minor validation errors for high-confidence candidates
                if errors > 3 or candidate.confidence < 0.7:
                    return f"Schema validation: {errors} errors"

        # 3. Business rules
        # Check required content
        title = data.get("title", "")
        if not title or len(title) < 5:
            return "Title missing or too short"

        content = data.get("content", [])
        if isinstance(content, list) and len(content) == 0:
            return "Content is empty"
        elif isinstance(content, str) and len(content) < 50:
            return "Content too short"

        # Check type is valid
        article_type = data.get("type", "")
        if article_type and article_type not in ("cikk", "edzesterv", "felszereles"):
            return f"Invalid type: {article_type}"

        # Check style is valid
        style = data.get("style", "")
        if style and style not in ("orszaguti", "mtb", "ciklokrossz", "altalanos"):
            return f"Invalid style: {style}"

        return None  # Valid

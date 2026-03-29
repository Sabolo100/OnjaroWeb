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

        # 3. Business rules - generic checks based on extracted data
        # title is required for all entity types
        title = data.get("title", "")
        if not title or len(title) < 2:
            return "Title missing or too short"

        # 4. Person-specific validation: reject headlines as person names
        if self._is_person_schema(schema_cls):
            rejection = self._validate_person_name(title, data)
            if rejection:
                return rejection

        # content should be present (list of paragraphs or text)
        content = data.get("content", [])
        if isinstance(content, list) and len(content) == 0:
            # Content is optional for some types, only reject if truly empty
            # and no other descriptive field exists
            pass
        elif isinstance(content, str) and len(content) < 10:
            return "Content too short"

        return None  # Valid

    def _is_person_schema(self, schema_cls) -> bool:
        """Check if schema is for a person entity."""
        if not schema_cls:
            return False
        name = schema_cls.__name__.lower()
        return "person" in name

    def _validate_person_name(self, title: str, data: dict) -> str:
        """Validate that a person 'title' field is an actual person name,
        not a news headline or sentence.

        A valid person name should:
        - Have 2-5 words (Hungarian/European names)
        - Not contain verbs or sentence-like patterns
        - Not be excessively long
        """
        words = title.strip().split()

        # Person name should be 2-5 words max
        if len(words) > 6:
            return f"Person name too long ({len(words)} words), likely a headline: '{title[:60]}'"

        # Should not be a sentence (contain common Hungarian verbs/articles)
        _SENTENCE_MARKERS = {
            "a", "az", "egy", "és", "vagy", "hogy", "volt", "lett", "van",
            "lesz", "nem", "sem", "is", "már", "még", "meg", "el", "ki",
            "be", "fel", "le", "át", "itt", "ott", "ezt", "azt", "aki",
            "ami", "ahol", "mint", "több", "új", "nagy", "magyar",
            "amely", "alapítottak", "megalakult", "megnyitott", "bezárt",
            "eladott", "felvásárolt", "bejelentette", "szervezetek",
        }
        lower_words = {w.lower().rstrip(".,;:!?") for w in words}
        sentence_overlap = lower_words & _SENTENCE_MARKERS
        if len(sentence_overlap) >= 2:
            return f"Person name appears to be a sentence (markers: {sentence_overlap}): '{title[:60]}'"

        # Name should contain at least one capital letter at the start of a word
        has_capital = any(w[0].isupper() for w in words if w)
        if not has_capital:
            return f"Person name has no capitalized words: '{title[:60]}'"

        return None

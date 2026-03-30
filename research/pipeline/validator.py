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
        # Name/title is required for all entity types
        name = data.get("name", data.get("title", ""))
        if not name or len(name) < 2:
            return "Name/title missing or too short"

        # 4. Reject headlines/sentences used as entity names (any type)
        if len(name.split()) > 10:
            return f"Name too long ({len(name.split())} words), likely a headline: '{name[:60]}'"

        # 5. Entity-specific validation
        schema_name = self._get_schema_name(schema_cls)

        if schema_name == "person":
            rejection = self._validate_person_name(name, data)
            if rejection:
                return rejection

        if schema_name == "company":
            rejection = self._validate_company_name(name, data)
            if rejection:
                return rejection

        if schema_name == "building":
            rejection = self._validate_building_name(name, data)
            if rejection:
                return rejection

        return None  # Valid

    def _get_schema_name(self, schema_cls) -> str:
        """Get the entity type from schema class name."""
        if not schema_cls:
            return ""
        name = schema_cls.__name__.lower()
        if "person" in name:
            return "person"
        if "company" in name:
            return "company"
        if "building" in name:
            return "building"
        return name

    def _validate_company_name(self, name: str, data: dict) -> str:
        """Reject companies that are not FM/PM/AM sector entities.

        Based on real cleanup findings: banks, utilities, IT companies,
        tobacco, gas storage, software vendors, generic words, and
        person names were all incorrectly extracted as companies.
        """
        lower = name.lower().strip()

        # Reject generic/meaningless words (< 3 chars or single common word)
        if len(lower) < 3:
            return f"Company name too short: '{name}'"

        _GENERIC_WORDS = {
            "nagyvállalat", "nagyvállalalat", "cég", "vállalat", "szervezet",
            "intézmény", "hivatal", "iroda", "szolgáltató",
        }
        if lower.rstrip(".") in _GENERIC_WORDS:
            return f"Generic word, not a company name: '{name}'"

        # Reject obvious non-FM/PM sectors
        _NON_FM_INDICATORS = [
            "bank", "takarék", "biztosító", "gyógyszer", "pharma",
            "vízmű", "vízművek", "gáztároló", "gázszolgáltató",
            "távhő", "főtáv", "erőmű", "áramszolgáltató",
            "tobacco", "dohány", "sörgyár", "élelmiszer",
        ]
        for indicator in _NON_FM_INDICATORS:
            if indicator in lower:
                return f"Non-FM/PM sector ({indicator}): '{name}'"

        return None

    def _validate_building_name(self, name: str, data: dict) -> str:
        """Reject building entries that are actually advertisements or listings.

        Based on real cleanup findings: classified ads (Kiadó/Eladó),
        generic descriptions, and non-building entries were extracted.
        """
        lower = name.lower().strip()

        # Reject classified ad patterns
        _AD_PREFIXES = [
            "kiadó ", "eladó ", "bérelhető ", "raktár kiadó",
            "iroda kiadó", "kiadó és eladó",
        ]
        for prefix in _AD_PREFIXES:
            if lower.startswith(prefix):
                return f"Classified ad, not a building name: '{name[:60]}'"

        # Reject if the name is a URL or domain
        if "http" in lower or ".hu" in lower or ".com" in lower:
            return f"URL in building name: '{name[:60]}'"

        # Reject names that are obviously project descriptions, not building names
        _DESCRIPTION_MARKERS = [
            "fejlesztés", "beruházás", "projekt", "pályázat",
            "tender", "közbeszerzés",
        ]
        # Only reject if these are the MAIN content (not part of a real name)
        words = lower.split()
        if len(words) >= 3 and words[-1].rstrip(".,") in _DESCRIPTION_MARKERS:
            # Check if there's a real building name in there
            if not any(w in lower for w in ["irodaház", "park", "központ", "ház", "tower", "palace", "center", "offices"]):
                return f"Project description, not a building: '{name[:60]}'"

        return None

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

        # Reject politicians / government officials (not FM/PM sector)
        # Check position_title (extraction field), not the person name
        position = data.get("position_title", "").lower()
        _POLITICIAN_TITLES = [
            "miniszter", "államtitkár", "képviselő", "polgármester",
            "alpolgármester", "miniszterelnök", "kormánybiztos",
            "országgyűlési", "parlamenti",
        ]
        for pt in _POLITICIAN_TITLES:
            if pt in position:
                return f"Government official, not FM/PM sector: '{title}' ({position[:40]})"

        return None

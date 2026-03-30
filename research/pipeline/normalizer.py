"""Research Normalizer - field mapping, cleaning, and normalization."""

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import List

from research.config_loader import ProjectConfig
from research.models import ExtractionCandidate

logger = logging.getLogger("onjaro.research.pipeline.normalizer")


class ContentNormalizer:
    """Normalizes extracted data for database persistence."""

    def __init__(self, config: ProjectConfig = None):
        self.config = config or ProjectConfig()

    def normalize(self, run_id: str, item: dict,
                  candidates: List[ExtractionCandidate]) -> List[ExtractionCandidate]:
        """Normalize all validated candidates."""
        target_table = item.get("target_table", "articles")
        mappings = self.config.load_mappings()
        table_config = mappings.get(target_table, {})

        for candidate in candidates:
            candidate.extracted_data = self._normalize_record(
                candidate.extracted_data, table_config
            )

        logger.info("Normalized %d candidates for table '%s'",
                    len(candidates), target_table)
        return candidates

    def _normalize_record(self, data: dict, table_config: dict) -> dict:
        """Normalize a single record's fields."""
        normalized = {}
        field_mapping = table_config.get("field_mapping", {})
        defaults = table_config.get("defaults", {})
        auto_fields = table_config.get("auto_fields", {})

        # Build set of allowed DB column names from mapping + defaults + auto_fields
        allowed_columns = set(field_mapping.values()) | set(defaults.keys()) | set(auto_fields.keys())

        # Apply field mapping: source_field -> target_field
        for source_field, target_field in field_mapping.items():
            if source_field in data:
                normalized[target_field] = data[source_field]

        # Only include unmapped fields if they match an allowed DB column name.
        # This prevents extra LLM-generated fields from leaking to Supabase.
        for key, value in data.items():
            if key not in field_mapping and key in allowed_columns and key not in normalized:
                normalized[key] = value

        # Apply defaults for missing fields
        for field, default_value in defaults.items():
            if field not in normalized or normalized[field] is None:
                normalized[field] = default_value

        # Auto-generate timestamp fields
        for field, strategy in auto_fields.items():
            if strategy == "auto_timestamp":
                normalized[field] = datetime.now(timezone.utc).isoformat()

        # Generic field-level normalization
        # Clean text fields (name, title, etc.)
        for field in ("name", "title", "entity_name"):
            if field in normalized and isinstance(normalized[field], str):
                normalized[field] = self._clean_text(normalized[field])

        # Normalize list-of-paragraphs fields → join into plain text for DB storage
        for field in ("description", "bio", "summary"):
            if field in normalized:
                normalized[field] = self._content_to_text(normalized[field])
        # Keep 'content' as list only if it's explicitly a list field not mapped to text
        if "content" in normalized:
            normalized["content"] = self._normalize_content(normalized["content"])

        # source_urls should always be a list
        if "source_urls" in normalized:
            val = normalized["source_urls"]
            if isinstance(val, str):
                normalized["source_urls"] = [val]
            elif not isinstance(val, list):
                normalized["source_urls"] = []

        # Empty string -> None for optional string fields to avoid enum/constraint violations
        for key, value in list(normalized.items()):
            if value == "" and key not in ("name", "title"):
                normalized[key] = None

        return normalized

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean and normalize text."""
        if not isinstance(text, str):
            return str(text) if text else ""
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _content_to_text(content) -> str:
        """Convert list of paragraphs or any content to a plain text string."""
        if isinstance(content, list):
            return " ".join(p.strip() for p in content if isinstance(p, str) and p.strip())
        if isinstance(content, str):
            return content.strip()
        return ""

    @staticmethod
    def _normalize_content(content) -> list:
        """Ensure content is a list of paragraphs."""
        if isinstance(content, list):
            return [p.strip() for p in content if isinstance(p, str) and p.strip()]
        if isinstance(content, str):
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
            return paragraphs
        return []

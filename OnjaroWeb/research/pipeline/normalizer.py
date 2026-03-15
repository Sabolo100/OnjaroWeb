"""Research Normalizer - field mapping, cleaning, and normalization."""

import hashlib
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

        # Apply field mapping
        for source_field, target_field in field_mapping.items():
            if source_field in data:
                normalized[target_field] = data[source_field]

        # Include unmapped fields that are in the data
        for key, value in data.items():
            if key not in field_mapping and key not in normalized:
                normalized[key] = value

        # Apply defaults for missing fields
        for field, default_value in defaults.items():
            if field not in normalized or normalized[field] is None:
                normalized[field] = default_value

        # Auto-generate fields
        for field, strategy in auto_fields.items():
            if strategy == "auto_generate" and field not in normalized:
                normalized[field] = self._generate_id(normalized)
            elif strategy == "auto_timestamp":
                normalized[field] = datetime.now(timezone.utc).isoformat()

        # Field-level normalization
        if "title" in normalized:
            normalized["title"] = self._clean_text(normalized["title"])

        if "excerpt" in normalized:
            normalized["excerpt"] = self._clean_text(normalized["excerpt"])
            if len(normalized["excerpt"]) > 500:
                normalized["excerpt"] = normalized["excerpt"][:497] + "..."

        if "content" in normalized:
            normalized["content"] = self._normalize_content(normalized["content"])

        if "word_count" in normalized and not normalized["word_count"]:
            normalized["word_count"] = self._count_words(normalized.get("content", []))

        if "date" in normalized and not normalized["date"]:
            normalized["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if "category_color" in normalized and not normalized["category_color"]:
            normalized["category_color"] = self._default_category_color(
                normalized.get("type", "cikk")
            )

        return normalized

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean and normalize text."""
        if not isinstance(text, str):
            return str(text) if text else ""
        # Normalize unicode
        text = unicodedata.normalize("NFC", text)
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

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

    @staticmethod
    def _count_words(content) -> int:
        """Count words in content."""
        if isinstance(content, list):
            return sum(len(p.split()) for p in content if isinstance(p, str))
        if isinstance(content, str):
            return len(content.split())
        return 0

    @staticmethod
    def _generate_id(data: dict) -> str:
        """Generate a unique ID based on content hash."""
        title = data.get("title", "")
        article_type = data.get("type", "cikk")
        prefix_map = {"cikk": "c", "edzesterv": "e", "felszereles": "f"}
        prefix = prefix_map.get(article_type, "x")
        hash_input = f"{title}:{article_type}"
        short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"{prefix}_{short_hash}"

    @staticmethod
    def _default_category_color(article_type: str) -> str:
        """Get default category color based on type."""
        return {
            "cikk": "bg-blue-100 text-blue-800",
            "edzesterv": "bg-green-100 text-green-800",
            "felszereles": "bg-amber-100 text-amber-800",
        }.get(article_type, "bg-gray-100 text-gray-800")

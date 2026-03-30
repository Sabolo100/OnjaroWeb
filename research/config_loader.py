"""Loads project-specific research configuration from YAML/Python files."""

import importlib.util
import logging
import os
from typing import Any, Dict, List, Optional, Type

import yaml
from pydantic import BaseModel

from research.config import RESEARCH_CONFIG_DIR
from research.models import (
    ResearchItem, SourceDefinition, ProjectPolicies,
    DedupePolicy, PersistencePolicy, ApprovalPolicy,
)

logger = logging.getLogger("onjaro.research.config_loader")


class ProjectConfig:
    """Loads and manages project-specific research configuration.

    Reads from: <webapp>/research_config/
    """

    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or RESEARCH_CONFIG_DIR
        self._items_cache = None
        self._policies_cache = None
        self._sources_cache = None
        self._schemas_cache = {}

    def _load_yaml(self, *path_parts: str) -> dict:
        """Load a YAML file relative to config_dir."""
        path = os.path.join(self.config_dir, *path_parts)
        if not os.path.exists(path):
            logger.warning("Config file not found: %s", path)
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # ── Research Items ──

    def load_items(self) -> List[dict]:
        """Load research item definitions from items.yaml."""
        if self._items_cache is not None:
            return self._items_cache

        data = self._load_yaml("items.yaml")
        raw_items = data.get("research_items", [])

        items = []
        for raw in raw_items:
            try:
                item = ResearchItem(**raw)
                items.append(item.model_dump())
            except Exception as e:
                logger.error("Invalid research item definition: %s - %s", raw.get("id", "?"), e)

        self._items_cache = items
        logger.info("Loaded %d research items from config", len(items))
        return items

    # ── Policies ──

    def load_policies(self) -> ProjectPolicies:
        """Load dedupe, persistence, and approval policies."""
        if self._policies_cache is not None:
            return self._policies_cache

        data = self._load_yaml("policies.yaml")

        self._policies_cache = ProjectPolicies(
            dedupe=DedupePolicy(**data.get("dedupe", {})),
            persistence=PersistencePolicy(**data.get("persistence", {})),
            approval=ApprovalPolicy(**data.get("approval", {})),
        )
        return self._policies_cache

    # ── Prompts ──

    def load_prompts(self, prompt_type: str) -> str:
        """Load a prompt template from prompts/<prompt_type>.yaml."""
        data = self._load_yaml("prompts", f"{prompt_type}.yaml")
        # Return the first key's value as the prompt string
        for key, value in data.items():
            if isinstance(value, str):
                return value
        return ""

    def load_search_prompts(self) -> dict:
        """Load search prompt templates."""
        return self._load_yaml("prompts", "search_prompts.yaml")

    def load_extract_prompts(self) -> dict:
        """Load extraction prompt templates."""
        return self._load_yaml("prompts", "extract_prompts.yaml")

    # ── Sources ──

    def load_sources(self) -> List[SourceDefinition]:
        """Load seed source definitions."""
        if self._sources_cache is not None:
            return self._sources_cache

        data = self._load_yaml("sources", "seed_sources.yaml")
        raw_sources = data.get("sources", [])

        sources = []
        for raw in raw_sources:
            try:
                sources.append(SourceDefinition(**raw))
            except Exception as e:
                logger.error("Invalid source definition: %s", e)

        self._sources_cache = sources
        logger.info("Loaded %d seed sources from config", len(sources))
        return sources

    # ── Extraction Schemas ──

    def load_schema(self, schema_name: str) -> Optional[Type[BaseModel]]:
        """Load a Pydantic schema model from schemas/<schema_name>.py.

        The file must contain a class named '<SchemaName>Candidate'
        (e.g., article.py contains ArticleCandidate).
        """
        if schema_name in self._schemas_cache:
            return self._schemas_cache[schema_name]

        schema_path = os.path.join(self.config_dir, "schemas", f"{schema_name}.py")
        if not os.path.exists(schema_path):
            logger.warning("Schema file not found: %s", schema_path)
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"research_schema_{schema_name}", schema_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for a class ending in 'Candidate'
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and issubclass(attr, BaseModel)
                        and attr is not BaseModel and attr_name.endswith("Candidate")):
                    self._schemas_cache[schema_name] = attr
                    logger.info("Loaded schema: %s from %s", attr_name, schema_path)
                    return attr

            logger.warning("No *Candidate class found in %s", schema_path)
            return None

        except Exception as e:
            logger.error("Failed to load schema '%s': %s", schema_name, e)
            return None

    # ── Mappings ──

    def load_mappings(self) -> dict:
        """Load field-to-DB-column mappings from mappings/persistence.yaml."""
        return self._load_yaml("mappings", "persistence.yaml")

    # ── Utility ──

    def reload(self):
        """Clear all caches, forcing reload on next access."""
        self._items_cache = None
        self._policies_cache = None
        self._sources_cache = None
        self._schemas_cache = {}

    def is_configured(self) -> bool:
        """Check if the project has research configuration."""
        return os.path.isdir(self.config_dir) and os.path.exists(
            os.path.join(self.config_dir, "items.yaml")
        )

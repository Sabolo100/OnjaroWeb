"""Factory for creating research connectors based on configuration."""

import logging

from research.connectors.base_connector import BaseConnector
from research.config import RESEARCH_AI_PLATFORM

logger = logging.getLogger("onjaro.research.connectors.factory")


def get_connector(platform: str = None) -> BaseConnector:
    """Get a search connector for the specified AI platform.

    Args:
        platform: "perplexity", "openai", "gemini", "claude"
                  If None, uses RESEARCH_AI_PLATFORM from config.

    Returns:
        A BaseConnector instance.
    """
    platform = (platform or RESEARCH_AI_PLATFORM).lower()

    if platform == "perplexity":
        from research.connectors.perplexity_connector import PerplexityConnector
        return PerplexityConnector()

    # Future connectors can be added here:
    # elif platform == "openai":
    #     from research.connectors.openai_connector import OpenAIConnector
    #     return OpenAIConnector()
    # elif platform == "gemini":
    #     from research.connectors.gemini_connector import GeminiConnector
    #     return GeminiConnector()

    raise ValueError(f"Unknown research AI platform: {platform}. "
                     f"Supported: perplexity")


def get_direct_fetcher():
    """Get a direct URL fetch connector."""
    from research.connectors.direct_fetch import DirectFetchConnector
    return DirectFetchConnector()

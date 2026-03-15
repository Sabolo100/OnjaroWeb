"""Perplexity AI search connector using OpenAI-compatible API."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

from research.connectors.base_connector import BaseConnector
from research.models import RawFinding
from research.config import (
    PERPLEXITY_API_KEY, PERPLEXITY_MODEL, PERPLEXITY_BASE_URL,
)

logger = logging.getLogger("onjaro.research.connectors.perplexity")


class PerplexityConnector(BaseConnector):
    """Search connector using Perplexity AI's API (OpenAI-compatible)."""

    name = "perplexity"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or PERPLEXITY_API_KEY
        self.model = model or PERPLEXITY_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=PERPLEXITY_BASE_URL,
                )
            except ImportError:
                raise RuntimeError("openai package required for Perplexity connector. pip install openai")
        return self._client

    def search(self, query: str, max_results: int = 5) -> List[RawFinding]:
        """Search Perplexity for content matching the query."""
        if not self.api_key:
            logger.error("Perplexity API key not set (PERPLEXITY_API_KEY)")
            return []

        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Return structured results as JSON. "
                            "For each result provide: url, title, snippet (2-3 sentence summary). "
                            f"Return up to {max_results} results as a JSON array."
                        ),
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
            )

            content = response.choices[0].message.content if response.choices else ""
            findings = self._parse_response(content, query)

            logger.info("Perplexity search returned %d findings for: %s",
                        len(findings), query[:80])
            return findings[:max_results]

        except Exception as e:
            logger.error("Perplexity search failed: %s", e)
            return []

    def fetch_url(self, url: str) -> str:
        """Fetch a URL's content via Perplexity summarization."""
        if not self.api_key:
            return ""

        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Summarize the content at the given URL in detail. Include all key information.",
                    },
                    {
                        "role": "user",
                        "content": f"Summarize the content at: {url}",
                    },
                ],
            )
            return response.choices[0].message.content if response.choices else ""
        except Exception as e:
            logger.error("Perplexity fetch_url failed for %s: %s", url, e)
            return ""

    def _parse_response(self, content: str, query: str) -> List[RawFinding]:
        """Parse Perplexity response into RawFinding objects."""
        findings = []
        now = datetime.now(timezone.utc)

        # Try to extract JSON array from response
        try:
            # Strip markdown code fences if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                inner = "\n".join(lines[1:])
                if "```" in inner:
                    inner = inner[:inner.rfind("```")]
                cleaned = inner.strip()

            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    findings.append(RawFinding(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        snippet=item.get("snippet", item.get("summary", "")),
                        content=item.get("content", ""),
                        source_domain=self._extract_domain(item.get("url", "")),
                        search_query=query,
                        connector_used=self.name,
                        fetched_at=now,
                    ))
                return findings
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: try to find JSON array in the text
        json_match = re.search(r'\[[\s\S]*?\]', content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            findings.append(RawFinding(
                                url=item.get("url", ""),
                                title=item.get("title", ""),
                                snippet=item.get("snippet", item.get("summary", "")),
                                source_domain=self._extract_domain(item.get("url", "")),
                                search_query=query,
                                connector_used=self.name,
                                fetched_at=now,
                            ))
                    return findings
            except (json.JSONDecodeError, TypeError):
                pass

        # Last resort: treat the entire response as a single finding
        if content.strip():
            findings.append(RawFinding(
                url="",
                title="Perplexity research result",
                snippet=content[:500] if len(content) > 500 else content,
                content=content,
                source_domain="perplexity.ai",
                search_query=query,
                connector_used=self.name,
                fetched_at=now,
            ))

        return findings

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc or ""
        except Exception:
            return ""

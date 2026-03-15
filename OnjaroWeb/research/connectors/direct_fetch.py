"""Direct URL fetch connector using httpx + BeautifulSoup."""

import logging
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

from research.connectors.base_connector import BaseConnector
from research.models import RawFinding
from research.config import FETCH_TIMEOUT_SECONDS

logger = logging.getLogger("onjaro.research.connectors.direct_fetch")


class DirectFetchConnector(BaseConnector):
    """Fetch and parse web pages directly."""

    name = "direct_fetch"

    def __init__(self, timeout: int = None):
        self.timeout = timeout or FETCH_TIMEOUT_SECONDS

    def search(self, query: str, max_results: int = 5) -> List[RawFinding]:
        """Direct fetch doesn't support search; use Perplexity for that."""
        logger.warning("DirectFetchConnector does not support search(). Use a search connector.")
        return []

    def fetch_url(self, url: str) -> str:
        """Fetch a URL and extract text content."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx package required. pip install httpx")
            return ""

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OnjaloResearchBot/1.0)"
                })
                response.raise_for_status()
                return self._extract_text(response.text, url)

        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return ""

    def fetch_as_finding(self, url: str, search_query: str = "") -> RawFinding:
        """Fetch a URL and return as a RawFinding."""
        content = self.fetch_url(url)
        title = self._extract_title(content) if content else ""

        return RawFinding(
            url=url,
            title=title,
            snippet=content[:300] if content else "",
            content=content,
            source_domain=self._extract_domain(url),
            search_query=search_query,
            connector_used=self.name,
            fetched_at=datetime.now(timezone.utc),
        )

    def _extract_text(self, html: str, url: str) -> str:
        """Extract readable text from HTML."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 package required. pip install beautifulsoup4")
            return html

        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, footer elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to get article content first
        article = soup.find("article") or soup.find("main") or soup.find("body")
        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def _extract_title(content: str) -> str:
        """Extract a title from text content (first non-empty line)."""
        for line in content.split("\n"):
            line = line.strip()
            if line and len(line) > 5:
                return line[:200]
        return ""

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            return urlparse(url).netloc or ""
        except Exception:
            return ""

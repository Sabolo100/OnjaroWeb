"""Research Fetcher - orchestrates the fetching phase of the pipeline."""

import logging
from typing import List
from urllib.parse import urlparse

from research.connectors.connector_factory import get_connector, get_direct_fetcher
from research.config_loader import ProjectConfig
from research.models import RawFinding
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.fetcher")


class ResearchFetcher:
    """Fetches raw data for research items using configured connectors."""

    def __init__(self, repo: ResearchRepository, config: ProjectConfig = None):
        self.repo = repo
        self.config = config or ProjectConfig()
        self._search_connector = None
        self._direct_fetcher = None

    def _get_search_connector(self):
        if self._search_connector is None:
            self._search_connector = get_connector()
        return self._search_connector

    def _get_direct_fetcher(self):
        if self._direct_fetcher is None:
            self._direct_fetcher = get_direct_fetcher()
        return self._direct_fetcher

    def fetch_for_item(self, run_id: str, item: dict) -> List[RawFinding]:
        """Fetch raw findings for a research item.

        Iterates through the item's topics, searches using the configured
        AI platform, deduplicates URLs, and stores raw findings to DB.
        """
        item_id = item.get("id", "unknown")
        topics = item.get("topics", [])
        max_results = item.get("max_results_per_run", 5)
        search_prompts = self.config.load_search_prompts()

        all_findings = []
        seen_urls = set()

        connector = self._get_search_connector()

        # Build search query template
        query_template = search_prompts.get("search_query_template", "{topic}")

        for topic in topics:
            try:
                query = query_template.format(
                    topic=topic,
                    max_results=max_results,
                )

                logger.info("Searching for item '%s', topic: %s", item_id, topic[:60])
                findings = connector.search(query, max_results=max_results)

                for finding in findings:
                    # Skip duplicate URLs within this run
                    normalized_url = self._normalize_url(finding.url)
                    if normalized_url in seen_urls:
                        continue
                    if normalized_url:
                        seen_urls.add(normalized_url)

                    # Store to DB
                    finding_id = self.repo.save_raw_finding(
                        run_id=run_id,
                        item_id=item_id,
                        url=finding.url,
                        title=finding.title,
                        snippet=finding.snippet,
                        content=finding.content,
                        source_domain=finding.source_domain,
                        search_query=topic,
                        connector_used=connector.name,
                    )
                    finding.finding_id = finding_id

                    # Update source registry
                    if finding.source_domain:
                        self.repo.upsert_source(
                            domain=finding.source_domain,
                            language=item.get("language", "hu"),
                        )

                    all_findings.append(finding)

                    if len(all_findings) >= max_results:
                        break

            except Exception as e:
                logger.error("Fetch failed for topic '%s': %s", topic[:60], e)
                continue

            if len(all_findings) >= max_results:
                break

        logger.info("Item '%s': fetched %d unique findings from %d topics",
                    item_id, len(all_findings), len(topics))
        return all_findings

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize a URL for deduplication."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            # Remove trailing slashes and fragments
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{path}"
        except Exception:
            return url

"""Abstract base class for research connectors."""

from abc import ABC, abstractmethod
from typing import List
from research.models import RawFinding


class BaseConnector(ABC):
    """Base class for all research data source connectors."""

    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[RawFinding]:
        """Search for content matching the query."""
        ...

    @abstractmethod
    def fetch_url(self, url: str) -> str:
        """Fetch content from a specific URL."""
        ...

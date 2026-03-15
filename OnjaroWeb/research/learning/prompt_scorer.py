"""Prompt Scorer - tracks effectiveness of search and extraction prompts."""

import hashlib
import logging

from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.learning.prompt_scorer")


class PromptScorer:
    """Tracks which prompts produce the best extraction results."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def record_result(self, prompt_text: str, prompt_type: str,
                      successful: bool, confidence: float = 0.0):
        """Record the result of a prompt execution."""
        prompt_hash = self._hash_prompt(prompt_text)
        self.repo.update_prompt_score(prompt_hash, prompt_type, successful, confidence)

    def get_effectiveness(self, prompt_text: str) -> dict:
        """Get effectiveness stats for a prompt (if available)."""
        prompt_hash = self._hash_prompt(prompt_text)
        # Would need a get method in repo - for now return empty
        return {"hash": prompt_hash, "tracked": True}

    @staticmethod
    def _hash_prompt(prompt_text: str) -> str:
        """Create a stable hash of a prompt template."""
        return hashlib.sha256(prompt_text.encode()).hexdigest()[:16]

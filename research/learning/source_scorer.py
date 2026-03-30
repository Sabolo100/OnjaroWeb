"""Source Scorer - tracks and updates source trust scores based on results."""

import logging

from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.learning.source_scorer")


class SourceScorer:
    """Manages source trust scores based on historical performance."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def update_scores_after_run(self, run_id: str):
        """Update source trust scores based on a completed run's results."""
        findings = self.repo.get_raw_findings_for_run(run_id)

        # Group findings by source domain
        domain_stats = {}
        for finding in findings:
            domain = finding.get("source_domain", "")
            if not domain:
                continue
            if domain not in domain_stats:
                domain_stats[domain] = {"total": 0, "successful": 0}
            domain_stats[domain]["total"] += 1

        # Check which findings led to persisted results
        persistence = self.repo.get_persistence_results(run_id)
        persisted_finding_ids = set()
        for p in persistence:
            if p.get("action") in ("inserted", "updated"):
                # Get the candidate's finding_id
                candidates = self.repo.get_candidates_for_run(run_id)
                for c in candidates:
                    if c.get("candidate_id") == p.get("candidate_id"):
                        persisted_finding_ids.add(c.get("finding_id"))

        for finding in findings:
            domain = finding.get("source_domain", "")
            if not domain:
                continue
            if finding.get("finding_id") in persisted_finding_ids:
                domain_stats[domain]["successful"] += 1

        # Calculate and update scores
        for domain, stats in domain_stats.items():
            success_rate = stats["successful"] / stats["total"] if stats["total"] > 0 else 0

            sources = self.repo.get_sources()
            current_source = next(
                (s for s in sources if s.get("domain") == domain), None
            )

            if current_source:
                # Weighted average: 70% historical, 30% new
                old_score = current_source.get("trust_score", 0.5)
                new_score = old_score * 0.7 + success_rate * 0.3
                new_score = max(0.1, min(1.0, round(new_score, 3)))
                self.repo.update_source_trust_score(domain, new_score)
                logger.info("Updated trust score for %s: %.3f -> %.3f",
                            domain, old_score, new_score)

    def get_ranked_sources(self, min_trust: float = 0.0) -> list:
        """Get sources ranked by trust score."""
        return self.repo.get_sources(min_trust=min_trust)

    def demote_source(self, domain: str, penalty: float = 0.2):
        """Reduce a source's trust score."""
        sources = self.repo.get_sources()
        source = next((s for s in sources if s.get("domain") == domain), None)
        if source:
            old_score = source.get("trust_score", 0.5)
            new_score = max(0.1, old_score - penalty)
            self.repo.update_source_trust_score(domain, new_score)
            logger.info("Demoted source %s: %.3f -> %.3f", domain, old_score, new_score)

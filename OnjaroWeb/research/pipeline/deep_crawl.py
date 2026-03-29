"""Deep Crawl - mine known companies for buildings and people.

After the standard research items are processed, this module looks at
companies already in Supabase that haven't been deeply crawled yet
(or were last crawled > 90 days ago).  For each eligible company it:

1. Searches for "<company_name> munkatársak csapat" → people
2. Searches for "<company_name> irodák épületek referenciák" → buildings
3. Records the crawl timestamp so the same company isn't re-crawled soon.

Results feed back into the standard extraction→validation→persist pipeline.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from research.supabase_client import get_supabase_client
from research.connectors.connector_factory import get_connector
from research.config_loader import ProjectConfig
from research.models import RawFinding
from db.research_repository import ResearchRepository

logger = logging.getLogger("onjaro.research.pipeline.deep_crawl")

# How long before re-crawling a company (days)
DEEP_CRAWL_COOLDOWN_DAYS = 90

# Max companies to deep-crawl per run
MAX_COMPANIES_PER_RUN = 3

# Search templates for deep crawl
_PEOPLE_QUERIES = [
    '"{company}" munkatársak csapat vezetőség',
    '"{company}" ügyvezető igazgató vezető',
]

_BUILDING_QUERIES = [
    '"{company}" referenciák kezelt irodaházak épületek',
    '"{company}" portfólió irodaház logisztikai park',
]


def get_companies_to_crawl(max_count: int = MAX_COMPANIES_PER_RUN) -> List[dict]:
    """Get companies from Supabase that haven't been deeply crawled recently.

    Returns list of dicts with id, name, website.
    """
    client = get_supabase_client()
    if not client:
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=DEEP_CRAWL_COOLDOWN_DAYS)).isoformat()

    try:
        # Get all companies
        resp = client.table("companies").select(
            "id,name,website,deep_crawled_at"
        ).execute()
        companies = resp.data or []

        # Filter: never crawled, or crawled before cutoff
        eligible = []
        for c in companies:
            crawled_at = c.get("deep_crawled_at")
            if not crawled_at or crawled_at < cutoff:
                eligible.append(c)

        # Sort: never-crawled first, then oldest crawl
        eligible.sort(key=lambda c: c.get("deep_crawled_at") or "")

        return eligible[:max_count]

    except Exception as e:
        # If the deep_crawled_at column doesn't exist yet, try without it
        if "deep_crawled_at" in str(e):
            logger.info("deep_crawled_at column not found, will crawl all companies")
            try:
                resp = client.table("companies").select("id,name,website").limit(max_count).execute()
                return resp.data or []
            except Exception as e2:
                logger.error("Failed to fetch companies for deep crawl: %s", e2)
                return []
        logger.error("Failed to fetch companies for deep crawl: %s", e)
        return []


def mark_company_crawled(company_id: str):
    """Update the deep_crawled_at timestamp for a company."""
    client = get_supabase_client()
    if not client:
        return

    now = datetime.now(timezone.utc).isoformat()
    try:
        client.table("companies").update(
            {"deep_crawled_at": now}
        ).eq("id", company_id).execute()
    except Exception as e:
        logger.warning("Could not update deep_crawled_at for %s: %s", company_id, e)


def generate_deep_crawl_items(companies: List[dict]) -> List[dict]:
    """Generate synthetic research items for deep-crawling companies.

    For each company, creates two virtual research items:
      - One for finding people (target: people table)
      - One for finding buildings (target: buildings table)
    """
    items = []

    for company in companies:
        name = company.get("name", "")
        company_id = company.get("id", "")
        if not name:
            continue

        # People search item
        items.append({
            "id": f"deep_crawl_people_{company_id[:12]}",
            "name": f"Deep crawl: {name} — munkatársak",
            "enabled": True,
            "priority": 10,
            "target_table": "people",
            "search_type": "topic_search",
            "schema_name": "person",
            "schedule": "manual",
            "max_results_per_run": 5,
            "topics": [q.format(company=name) for q in _PEOPLE_QUERIES],
            "language": "hu",
            "content_types": ["person"],
            "min_confidence": 0.6,
            "auto_approve_above": 0.8,
            "manual_review_below": 0.4,
            "_deep_crawl_company_id": company_id,
            "_deep_crawl_company_name": name,
        })

        # Buildings search item
        items.append({
            "id": f"deep_crawl_buildings_{company_id[:12]}",
            "name": f"Deep crawl: {name} — épületek",
            "enabled": True,
            "priority": 10,
            "target_table": "buildings",
            "search_type": "topic_search",
            "schema_name": "building",
            "schedule": "manual",
            "max_results_per_run": 5,
            "topics": [q.format(company=name) for q in _BUILDING_QUERIES],
            "language": "hu",
            "content_types": ["building"],
            "min_confidence": 0.6,
            "auto_approve_above": 0.8,
            "manual_review_below": 0.4,
            "_deep_crawl_company_id": company_id,
            "_deep_crawl_company_name": name,
        })

    return items

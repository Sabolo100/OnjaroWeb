"""Dedicated enrichment script for skeleton companies.

Skeleton companies (confidence <= 0.45, no description/website) were
auto-created when a person was linked to them.  The standard deep crawl
uses FM-specific queries that don't work for developers, asset managers,
or investment funds.  This script uses broader, company-type-agnostic
queries and runs without MAX_COMPANIES_PER_RUN limits.

Usage:
    source .env && export SUPABASE_URL SUPABASE_SERVICE_KEY PERPLEXITY_API_KEY
    python3 scripts/enrich_skeleton_companies.py [--dry-run] [--company "Name"]
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("enrich")


# ── Query templates ──────────────────────────────────────────────────────────
# Broad queries that work for FM companies, developers, funds, and brokers.
# Using 3 angles: identity/website, portfolio/buildings, people.

_ENRICH_QUERIES = [
    # Website & basic info
    '"{company}" official website cég bemutatkozás tevékenység Budapest',
    # Portfolio / buildings
    '"{company}" kezelt épületek ingatlan portfólió fejlesztés irodaház',
    # People / leadership
    '"{company}" vezető igazgató ügyvezető management csapat',
]

# Fields that count as "has real data"
_ENRICHABLE = {
    "description": lambda v: bool(v and len(str(v)) > 20),
    "service_types": lambda v: bool(v and len(v) > 0),
    "website": lambda v: bool(v),
    "headquarters_city": lambda v: bool(v),
    "headquarters_address": lambda v: bool(v),
    "founded_year": lambda v: bool(v),
    "employee_count_estimate": lambda v: bool(v),
    "is_international": lambda v: v is True,
    "name_aliases": lambda v: bool(v and len(v) > 0),
}

SKELETON_THRESHOLD = 0.45


def get_skeleton_companies(client, name_filter: str = None):
    resp = client.table("companies").select(
        "id,name,confidence,description,website,service_types"
    ).execute()
    companies = resp.data or []

    result = []
    for co in companies:
        conf = co.get("confidence") or 0.5
        if conf > SKELETON_THRESHOLD:
            continue
        desc = co.get("description") or ""
        web = co.get("website") or ""
        svcs = co.get("service_types") or []
        # Skip if already has enough data
        has_data = len(desc) > 20 or web or len(svcs) > 0
        if has_data:
            continue
        if name_filter and name_filter.lower() not in co["name"].lower():
            continue
        result.append(co)

    return result


_DIRECT_PROMPT = """Adj strukturált JSON adatokat a következő magyar ingatlanpiaci cégről: "{company}"

Keress minden elérhető forrásból (weboldal, cikkek, LinkedIn, cégadatbázis) és adj vissza JSON-t:
{{
  "name": "cég hivatalos neve",
  "description": "2-4 mondat a cég tevékenységéről magyarul",
  "website": "https://...",
  "headquarters_city": "város neve",
  "service_types": ["fm" és/vagy "pm" és/vagy "am" — csak ha ténylegesen nyújt ilyen szolgáltatást],
  "is_international": true/false,
  "founded_year": évszám vagy null,
  "managed_properties": ["épület1", "épület2", ...],
  "key_people": [
    {{"name": "Teljes Név", "position_title": "Pozíció"}}
  ]
}}

Ha valamit nem tudsz biztosan, hagyd null-ra. Csak JSON-t adj vissza, semmi mást."""


def query_company_direct(connector, company_name: str) -> dict:
    """Ask Perplexity directly for structured company data (no web scraping)."""
    prompt = _DIRECT_PROMPT.format(company=company_name)
    logger.info("  Direct query for: %s", company_name)

    try:
        client = connector._get_client()
        response = client.chat.completions.create(
            model=connector.model,
            messages=[
                {"role": "system", "content": (
                    "Te egy magyar ingatlanpiaci adatbázis-feltöltő asszisztens vagy. "
                    "Mindig strukturált JSON-t adj vissza a kért mezőkkel."
                )},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content if response.choices else ""

        # Parse JSON
        import re
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if "```" in text:
                text = text[:text.rfind("```")]
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logger.warning("  Direct query failed: %s", e)
    return {}


def merge_into_existing(client, company_id: str, company_name: str,
                        candidates, normalizer, item: dict, dry_run: bool):
    """Merge best candidate data into the existing skeleton record."""
    if not candidates:
        return 0

    # Normalize all candidates
    if normalizer:
        candidates = normalizer.normalize("enrich", item, candidates)

    # Pick highest confidence
    best = max(candidates, key=lambda c: c.confidence)
    data = best.extracted_data
    conf = best.confidence

    logger.info("  Best candidate: conf=%.2f, name='%s'", conf, data.get("name", "?"))

    # Fetch current DB record
    try:
        existing_resp = client.table("companies").select("*").eq("id", company_id).execute()
        if not existing_resp.data:
            logger.warning("  Company %s not found in DB", company_id)
            return 0
        record = existing_resp.data[0]
    except Exception as e:
        logger.error("  DB fetch failed: %s", e)
        return 0

    # Build updates — only fill empty fields
    updates = {}
    for field, has_value in _ENRICHABLE.items():
        existing_val = record.get(field)
        new_val = data.get(field)
        if not has_value(existing_val) and has_value(new_val):
            updates[field] = new_val
            logger.info("  + %s: %s", field, str(new_val)[:80])

    if not updates:
        logger.info("  No new data found for '%s'", company_name)
        return 0

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now
    updates["last_confirmed_at"] = now
    if (record.get("confidence") or 0) < 0.5:
        updates["confidence"] = 0.5

    if dry_run:
        logger.info("  [DRY RUN] Would update %d fields", len(updates) - 2)
        return 1

    try:
        client.table("companies").update(updates).eq("id", company_id).execute()
        logger.info("  ✓ Updated %d fields for '%s'", len(updates) - 2, company_name)
        return 1
    except Exception as e:
        logger.error("  Update failed: %s", e)
        return 0


def process_key_people(client, company_id: str, candidates, persister, dry_run: bool):
    """Extract and persist key_people found during enrichment."""
    from research.config_loader import ProjectConfig
    config = ProjectConfig()
    mappings = config.load_mappings()
    company_config = mappings.get("companies", {})
    related_cfg = company_config.get("related_entities", {}).get("key_people", {})
    if not related_cfg or not persister:
        return 0

    added = 0
    for candidate in candidates:
        key_people = candidate.extracted_data.get("_key_people") or []
        if key_people:
            if not dry_run:
                persister._process_related_entities(
                    client, company_id, "companies",
                    key_people, related_cfg, {"source_urls": []},
                )
            added += len(key_people)
            logger.info("  ✓ Processed %d key_people", len(key_people))
    return added


def main():
    parser = argparse.ArgumentParser(description="Enrich skeleton companies")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing to DB")
    parser.add_argument("--company", type=str, default=None,
                        help="Filter to a specific company name (substring match)")
    parser.add_argument("--max", type=int, default=0,
                        help="Max companies to process (0 = all)")
    args = parser.parse_args()

    # ── Setup ──
    from research.supabase_client import get_supabase_client
    from research.connectors.connector_factory import get_connector
    from research.pipeline.extractor import ResearchExtractor
    from research.pipeline.normalizer import ContentNormalizer
    from research.pipeline.persister import ResearchPersister
    from research.config_loader import ProjectConfig
    from db.research_repository import ResearchRepository

    client = get_supabase_client()
    if not client:
        logger.error("No Supabase client — set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    repo = ResearchRepository()
    config = ProjectConfig()
    connector = get_connector()
    extractor = ResearchExtractor(repo, config)
    normalizer = ContentNormalizer(config)
    persister = ResearchPersister(repo, config)

    import uuid
    run_id = f"enrich_{uuid.uuid4().hex[:8]}"

    # ── Find skeleton companies ──
    companies = get_skeleton_companies(client, args.company)
    if not companies:
        logger.info("No skeleton companies found — nothing to do.")
        return

    if args.max > 0:
        companies = companies[:args.max]

    logger.info("=" * 60)
    logger.info("Enriching %d skeleton companies (run_id=%s, dry_run=%s)",
                len(companies), run_id, args.dry_run)
    logger.info("=" * 60)

    total_updated = 0
    total_people = 0

    for i, company in enumerate(companies, 1):
        cid = company["id"]
        name = company["name"]
        logger.info("\n[%d/%d] %s (%s)", i, len(companies), name, cid[:12])

        # Direct structured query — bypasses FM-specific extraction prompt
        raw = query_company_direct(connector, name)
        if not raw:
            logger.info("  No data returned for '%s'", name)
            continue

        logger.info("  Got data: desc=%dch  web=%s  svcs=%s  people=%d  buildings=%d",
                    len(raw.get("description") or ""),
                    raw.get("website") or "-",
                    raw.get("service_types") or [],
                    len(raw.get("key_people") or []),
                    len(raw.get("managed_properties") or []))

        # Fetch current DB record
        try:
            existing_resp = client.table("companies").select("*").eq("id", cid).execute()
            if not existing_resp.data:
                continue
            record = existing_resp.data[0]
        except Exception as e:
            logger.error("  DB fetch failed: %s", e)
            continue

        # Build updates — only fill empty fields
        updates = {}
        field_map = {
            "description": ("description", lambda v: bool(v and len(str(v)) > 20)),
            "service_types": ("service_types", lambda v: bool(v and len(v) > 0)),
            "website": ("website", lambda v: bool(v)),
            "headquarters_city": ("headquarters_city", lambda v: bool(v)),
            "is_international": ("is_international", lambda v: v is True),
            "founded_year": ("founded_year", lambda v: bool(v)),
        }

        for raw_key, (db_col, has_value) in field_map.items():
            existing_val = record.get(db_col)
            new_val = raw.get(raw_key)
            if not has_value(existing_val) and has_value(new_val):
                updates[db_col] = new_val
                logger.info("  + %s: %s", db_col, str(new_val)[:80])

        if updates:
            now = datetime.now(timezone.utc).isoformat()
            updates["updated_at"] = now
            updates["last_confirmed_at"] = now
            if (record.get("confidence") or 0) < 0.5:
                updates["confidence"] = 0.5

            if not args.dry_run:
                try:
                    client.table("companies").update(updates).eq("id", cid).execute()
                    logger.info("  ✓ Updated %d fields", len(updates) - 2)
                    total_updated += 1
                except Exception as e:
                    logger.error("  Update failed: %s", e)
            else:
                logger.info("  [DRY RUN] Would update %d fields", len(updates) - 2)
                total_updated += 1
        else:
            logger.info("  No new fields to update for '%s'", name)

        # Handle managed_properties — search/create building stubs
        managed = raw.get("managed_properties") or []
        if managed:
            logger.info("  Found %d managed properties: %s",
                        len(managed), ", ".join(managed[:5]))

        # Handle key_people
        key_people = raw.get("key_people") or []
        if key_people and not args.dry_run:
            from research.config_loader import ProjectConfig
            cfg = ProjectConfig()
            mappings = cfg.load_mappings()
            company_cfg = mappings.get("companies", {})
            related_cfg = company_cfg.get("related_entities", {}).get("key_people", {})
            if related_cfg:
                persister._process_related_entities(
                    client, cid, "companies",
                    key_people, related_cfg, {"source_urls": []},
                )
                total_people += len(key_people)
                logger.info("  ✓ Processed %d key_people", len(key_people))
        elif key_people and args.dry_run:
            logger.info("  [DRY RUN] Would process %d key_people: %s",
                        len(key_people),
                        ", ".join(p.get("name", "?") for p in key_people[:3]))

    # ── Summary ──
    logger.info("\n" + "=" * 60)
    logger.info("Done: %d/%d companies updated, %d people processed",
                total_updated, len(companies), total_people)
    if args.dry_run:
        logger.info("(DRY RUN — no changes were written)")


if __name__ == "__main__":
    main()

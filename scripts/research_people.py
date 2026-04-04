"""Dedicated people research script — multi-channel discovery.

Systematically finds professionals at companies already in the database
through multiple channels: company websites, Perplexity search, and
conference speaker lists.

Usage:
    source .env && export SUPABASE_URL SUPABASE_SERVICE_KEY PERPLEXITY_API_KEY
    python3 scripts/research_people.py [--dry-run] [--channel website|search|conference|all]
"""

import sys
import os
import json
import re
import time
import argparse
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("research_people")

# ── Progress file ────────────────────────────────────────────────────────────
PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", ".people_research_progress.json",
)

# ── Team page paths to try on company websites ──────────────────────────────
_TEAM_PAGE_PATHS = [
    "/rolunk/vezetoseg", "/rolunk/csapat", "/rolunk/csapatunk", "/rolunk",
    "/about/team", "/about/leadership", "/about/management", "/about-us",
    "/team", "/our-team", "/people", "/leadership", "/management",
    "/contact", "/kapcsolat", "/kontakt",
    "/en/about/team", "/en/team", "/en/about-us", "/en/leadership",
    "/hu/rolunk", "/hu/csapat",
    "",  # homepage as last resort
]

# ── Confidence levels ────────────────────────────────────────────────────────
CONFIDENCE_WEBSITE = 0.75
CONFIDENCE_SEARCH = 0.60
CONFIDENCE_CONFERENCE = 0.65

# ── Valid position categories (from person schema) ───────────────────────────
VALID_CATEGORIES = {
    "ceo", "coo", "cfo", "cto",
    "fm_director", "pm_director", "am_director",
    "fm_manager", "pm_manager", "am_manager",
    "regional_director", "country_manager",
    "head_of_operations", "head_of_technical",
    "board_member", "partner",
    "business_development", "leasing_manager", "other",
}

# ── Conference search queries ────────────────────────────────────────────────
_CONFERENCE_QUERIES = [
    "FM konferencia előadó Magyarország 2024 2025 2026 facility management",
    "ingatlan property management konferencia Budapest előadók",
    "IFMA Hungary konferencia program előadó",
    "Portfolio Property konferencia előadó panel",
    "Facility Management Fórum előadók résztvevők",
    "kereskedelmi ingatlan konferencia 2025 2026 Budapest panelbeszélgetés",
]

# ── Prompts ──────────────────────────────────────────────────────────────────

_WEBSITE_EXTRACT_PROMPT = """Adj strukturált JSON adatokat a következő weboldal szövegéből kinyerhető SZEMÉLYEKRŐL.
Ez a(z) "{company}" cég weboldala.

Keress MINDEN említett személyt (vezetők, igazgatók, menedzserek, csapattagok, kapcsolattartók).

Adj vissza JSON-t:
{{
  "people": [
    {{
      "name": "Teljes Név (keresztnév és vezetéknév)",
      "position_title": "Pozíció pontos megnevezése",
      "position_category": "ceo/coo/cfo/cto/fm_director/pm_director/am_director/fm_manager/pm_manager/am_manager/regional_director/country_manager/head_of_operations/head_of_technical/board_member/partner/business_development/leasing_manager/other",
      "email": "email@example.com vagy null",
      "phone": "telefonszám vagy null",
      "linkedin_url": "LinkedIn profil URL vagy null",
      "bio": "rövid leírás ha elérhető, vagy null"
    }}
  ]
}}

FONTOS:
- Csak valódi SZEMÉLYEKET adj vissza (keresztnév + vezetéknév), NE cégneveket vagy részlegeket
- Ha nem találsz személyeket, adj vissza {{"people": []}}
- Csak JSON-t adj vissza, semmi mást

WEBOLDAL SZÖVEG:
---
{text}"""

_SEARCH_PROMPT = """Keress MINDEN nyilvánosan elérhető információt a(z) "{company}" cég vezetőiről
és kulcsembereiről a magyar ingatlanpiacon (facility management, property management, asset management szektor).

Keress a cég weboldalán, LinkedIn-en, hírekben, sajtóközleményekben, konferencia előadók között.

Adj vissza JSON-t:
{{
  "people": [
    {{
      "name": "Teljes Név (keresztnév és vezetéknév)",
      "position_title": "Pozíció pontos megnevezése",
      "position_category": "ceo/coo/cfo/cto/fm_director/pm_director/am_director/fm_manager/pm_manager/am_manager/regional_director/country_manager/head_of_operations/head_of_technical/board_member/partner/business_development/leasing_manager/other",
      "linkedin_url": "LinkedIn profil URL vagy null",
      "source_description": "honnan származik az adat (pl. 'cég weboldal', 'LinkedIn', 'portfolio.hu cikk')"
    }}
  ]
}}

FONTOS:
- Csak valódi, azonosítható SZEMÉLYEKET adj vissza (teljes név szükséges)
- Ha nem találsz senkit, adj vissza {{"people": []}}
- Csak JSON-t adj vissza, semmi mást"""

_CONFERENCE_PROMPT = """Keress előadókat, panelbeszélgetés résztvevőket és szervezőket
a következő témájú magyar ingatlanpiaci / facility management konferenciákon:

"{query}"

Adj vissza JSON-t minden talált személyről:
{{
  "people": [
    {{
      "name": "Teljes Név",
      "position_title": "Pozíció és cég neve",
      "company_name": "Cég neve ahol dolgozik",
      "position_category": "ceo/coo/cfo/cto/fm_director/pm_director/am_director/fm_manager/pm_manager/am_manager/regional_director/country_manager/head_of_operations/head_of_technical/board_member/partner/business_development/leasing_manager/other",
      "conference_name": "Konferencia neve",
      "source_description": "forrás URL vagy leírás"
    }}
  ]
}}

FONTOS:
- Csak valódi, azonosítható SZEMÉLYEKET adj vissza (teljes név szükséges)
- Ha nem találsz senkit, adj vissza {{"people": []}}
- Csak JSON-t adj vissza, semmi mást"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_accents(s):
    """Remove Hungarian accents for comparison."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.category(c).startswith("M"))


def names_match(a, b, threshold=0.85):
    """Check if two person names match (case-insensitive, accent-insensitive)."""
    a_norm = strip_accents(a.strip().lower())
    b_norm = strip_accents(b.strip().lower())
    if a_norm == b_norm:
        return True
    # Token-based: all tokens of shorter name present in longer
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    shorter, longer = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    if len(shorter) >= 2 and shorter.issubset(longer):
        return True
    return SequenceMatcher(None, a_norm, b_norm).ratio() >= threshold


def parse_json_response(text):
    """Parse JSON from an AI response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if "```" in text:
            text = text[:text.rfind("```")]
        text = text.strip()
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {}


def compute_confidence(base, person_data):
    """Adjust confidence based on available data."""
    conf = base
    if person_data.get("linkedin_url"):
        conf += 0.10
    if person_data.get("email"):
        conf += 0.05
    return min(conf, 0.95)


def clean_position_category(cat):
    """Validate and clean position_category."""
    if not cat:
        return None
    cat = cat.strip().lower().replace(" ", "_").replace("-", "_")
    return cat if cat in VALID_CATEGORIES else "other"


def load_progress():
    """Load progress tracking from JSON file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_progress(progress):
    """Save progress tracking to JSON file."""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


# ── Channel 1: Company Website ──────────────────────────────────────────────

def discover_from_website(connector, fetcher, company_name, website_url):
    # type: (...) -> List[Dict[str, Any]]
    """Scrape company website team/leadership pages for people."""
    if not website_url:
        return []

    # Normalize base URL — handle URLs with existing paths like /en/
    raw_url = website_url.rstrip("/")
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url

    from urllib.parse import urlparse
    parsed = urlparse(raw_url)
    domain_base = "%s://%s" % (parsed.scheme, parsed.netloc)
    url_path = parsed.path.rstrip("/")

    found_people = []

    # Build list of candidate URLs to try
    candidate_urls = []
    seen_urls = set()
    for path in _TEAM_PAGE_PATHS:
        urls_to_add = []
        if url_path and path:
            urls_to_add.append(domain_base + url_path + path)
            urls_to_add.append(domain_base + path)
        elif path:
            urls_to_add.append(domain_base + path)
        else:
            urls_to_add.append(raw_url)
        for u in urls_to_add:
            if u not in seen_urls:
                seen_urls.add(u)
                candidate_urls.append(u)

    for url in candidate_urls:
        logger.info("    Trying: %s", url)
        time.sleep(1.0)  # rate limit

        text = fetcher.fetch_url(url)
        if not text or len(text) < 100:
            continue

        logger.info("    Fetched %d chars from %s", len(text), url)

        # Send to Perplexity for extraction
        prompt = _WEBSITE_EXTRACT_PROMPT.format(company=company_name, text=text[:8000])
        time.sleep(0.5)

        try:
            client = connector._get_client()
            response = client.chat.completions.create(
                model=connector.model,
                messages=[
                    {"role": "system", "content": (
                        "Te egy magyar ingatlanpiaci adatbázis-feltöltő asszisztens vagy. "
                        "Mindig strukturált JSON-t adj vissza a kért formátumban."
                    )},
                    {"role": "user", "content": prompt},
                ],
            )
            resp_text = response.choices[0].message.content if response.choices else ""
            data = parse_json_response(resp_text)
            people = data.get("people") or []

            if people:
                logger.info("    Found %d people on %s", len(people), url)
                for p in people:
                    p["_source_url"] = url
                    p["_channel"] = "website"
                found_people.extend(people)
                break  # Stop after first page with results

        except Exception as e:
            logger.warning("    Extraction failed for %s: %s", url, e)
            continue

    return found_people


# ── Channel 2: Perplexity Search ────────────────────────────────────────────

def discover_from_search(connector, company_name):
    # type: (...) -> List[Dict[str, Any]]
    """Search Perplexity for people at a specific company."""
    prompt = _SEARCH_PROMPT.format(company=company_name)

    try:
        client = connector._get_client()
        response = client.chat.completions.create(
            model=connector.model,
            messages=[
                {"role": "system", "content": (
                    "Te egy magyar ingatlanpiaci adatbázis-feltöltő asszisztens vagy. "
                    "Mindig strukturált JSON-t adj vissza a kért formátumban."
                )},
                {"role": "user", "content": prompt},
            ],
        )
        resp_text = response.choices[0].message.content if response.choices else ""
        data = parse_json_response(resp_text)
        people = data.get("people") or []

        for p in people:
            p["_channel"] = "search"
            p["_source_url"] = p.get("source_description") or "perplexity search"

        return people

    except Exception as e:
        logger.warning("  Search failed for '%s': %s", company_name, e)
        return []


# ── Channel 3: Conference Speakers ──────────────────────────────────────────

def discover_from_conferences(connector):
    # type: (...) -> List[Dict[str, Any]]
    """Search for conference speakers across FM/PM/AM events."""
    all_people = []

    for query in _CONFERENCE_QUERIES:
        logger.info("  Conference query: %s", query[:60])
        prompt = _CONFERENCE_PROMPT.format(query=query)
        time.sleep(0.5)

        try:
            client = connector._get_client()
            response = client.chat.completions.create(
                model=connector.model,
                messages=[
                    {"role": "system", "content": (
                        "Te egy magyar ingatlanpiaci kutatási asszisztens vagy. "
                        "Mindig strukturált JSON-t adj vissza a kért formátumban."
                    )},
                    {"role": "user", "content": prompt},
                ],
            )
            resp_text = response.choices[0].message.content if response.choices else ""
            data = parse_json_response(resp_text)
            people = data.get("people") or []

            for p in people:
                p["_channel"] = "conference"
                p["_source_url"] = p.get("source_description") or "conference search"

            logger.info("    Found %d speakers", len(people))
            all_people.extend(people)

        except Exception as e:
            logger.warning("    Conference query failed: %s", e)

    return all_people


# ── Persistence ──────────────────────────────────────────────────────────────

def persist_people(client, persister, company_id, company_name,
                   people, base_confidence, source_label, dry_run):
    # type: (...) -> Tuple[int, int]
    """Persist discovered people to Supabase. Returns (new_count, updated_count)."""
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    updated_count = 0

    for person_data in people:
        name = (person_data.get("name") or "").strip()
        if not name or len(name) < 4:
            continue

        # Basic validation: must look like a real name (2+ parts)
        parts = name.split()
        if len(parts) < 2:
            logger.debug("    Skipping single-word name: '%s'", name)
            continue

        position_title = (person_data.get("position_title") or "").strip() or None
        position_category = clean_position_category(person_data.get("position_category"))
        confidence = compute_confidence(base_confidence, person_data)
        source_url = person_data.get("_source_url") or source_label
        source_urls = [source_url] if source_url else []

        if dry_run:
            logger.info("    [DRY RUN] Would persist: '%s' — %s (%s, conf=%.2f)",
                        name, position_title or "?", position_category or "?", confidence)
            new_count += 1
            continue

        # Use persister's _find_or_create_person (handles dedup)
        try:
            person_id = persister._find_or_create_person(
                client,
                person_table="people",
                name=name,
                company_id=company_id,
                position_title=position_title,
                defaults={"confidence": confidence},
                source_urls=source_urls,
                now_iso=now,
            )
            if not person_id:
                continue

            # Also update extra fields if available
            extra_updates = {}
            if person_data.get("linkedin_url"):
                extra_updates["linkedin_url"] = person_data["linkedin_url"]
            if person_data.get("email"):
                extra_updates["email"] = person_data["email"]
            if person_data.get("phone"):
                extra_updates["phone"] = person_data["phone"]
            if person_data.get("bio"):
                extra_updates["bio"] = person_data["bio"]

            if extra_updates:
                # Only update fields that are currently empty
                try:
                    resp = client.table("people").select(
                        ",".join(extra_updates.keys())
                    ).eq("id", person_id).execute()
                    if resp.data:
                        existing = resp.data[0]
                        filtered_updates = {
                            k: v for k, v in extra_updates.items()
                            if not existing.get(k)
                        }
                        if filtered_updates:
                            filtered_updates["updated_at"] = now
                            client.table("people").update(filtered_updates).eq(
                                "id", person_id).execute()
                except Exception as e:
                    logger.debug("    Extra field update failed: %s", e)

            # Create/update job record
            persister._find_or_create_job(
                client,
                jobs_table="jobs",
                person_id=person_id,
                company_id=company_id,
                position_title=position_title,
                position_category=position_category,
                defaults={"is_current": True, "confidence": confidence},
                source_urls=source_urls,
                now_iso=now,
            )

            new_count += 1
            logger.info("    + %s — %s", name, position_title or "?")

        except Exception as e:
            logger.error("    Failed to persist '%s': %s", name, e)

    return new_count, updated_count


def persist_conference_people(client, persister, people, dry_run):
    # type: (...) -> int
    """Persist conference speakers, resolving their company from name."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    # Load all companies for matching
    try:
        resp = client.table("companies").select("id,name").execute()
        all_companies = resp.data or []
    except Exception as e:
        logger.error("  Failed to load companies: %s", e)
        return 0

    for person_data in people:
        name = (person_data.get("name") or "").strip()
        company_name = (person_data.get("company_name") or "").strip()
        if not name or len(name) < 4:
            continue
        parts = name.split()
        if len(parts) < 2:
            continue

        position_title = (person_data.get("position_title") or "").strip() or None
        position_category = clean_position_category(person_data.get("position_category"))
        confidence = compute_confidence(CONFIDENCE_CONFERENCE, person_data)
        source_url = person_data.get("_source_url") or "conference"
        source_urls = [source_url] if source_url else []

        # Try to match company
        company_id = None
        if company_name:
            from research.pipeline.deduplicator import normalize_company_name
            norm_target = normalize_company_name(company_name)
            for co in all_companies:
                if normalize_company_name(co["name"]) == norm_target:
                    company_id = co["id"]
                    break

        if dry_run:
            matched = "-> %s" % company_id[:12] if company_id else "(no company match)"
            logger.info("    [DRY RUN] Conference: '%s' @ '%s' %s",
                        name, company_name or "?", matched)
            count += 1
            continue

        if not company_id:
            # Skip people we can't link to a known company
            logger.debug("    Skipping '%s' — company '%s' not in DB", name, company_name)
            continue

        try:
            person_id = persister._find_or_create_person(
                client, person_table="people", name=name,
                company_id=company_id, position_title=position_title,
                defaults={"confidence": confidence},
                source_urls=source_urls, now_iso=now,
            )
            if person_id:
                persister._find_or_create_job(
                    client, jobs_table="jobs", person_id=person_id,
                    company_id=company_id, position_title=position_title,
                    position_category=position_category,
                    defaults={"is_current": True, "confidence": confidence},
                    source_urls=source_urls, now_iso=now,
                )
                count += 1
                logger.info("    + %s @ %s — %s", name, company_name, position_title or "?")
        except Exception as e:
            logger.error("    Failed to persist conference person '%s': %s", name, e)

    return count


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Research people at known companies")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing to DB")
    parser.add_argument("--company", type=str, default=None,
                        help="Filter to a specific company name (substring match)")
    parser.add_argument("--max", type=int, default=0,
                        help="Max companies to process (0 = all)")
    parser.add_argument("--channel", type=str, default="all",
                        choices=["website", "search", "conference", "all"],
                        help="Which channel to use (default: all)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip companies that already have >= 3 people linked")
    args = parser.parse_args()

    # ── Setup ──
    from research.supabase_client import get_supabase_client
    from research.connectors.connector_factory import get_connector, get_direct_fetcher
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
    fetcher = get_direct_fetcher()
    persister = ResearchPersister(repo, config)

    progress = load_progress()

    # ── Load companies ──
    resp = client.table("companies").select(
        "id,name,website,service_types"
    ).execute()
    companies = resp.data or []

    if args.company:
        companies = [c for c in companies
                     if args.company.lower() in c["name"].lower()]

    if not companies:
        logger.info("No companies found — nothing to do.")
        return

    # Optionally skip companies with enough people already
    if args.skip_existing:
        resp_jobs = client.table("jobs").select(
            "company_id", count="exact"
        ).eq("is_current", True).execute()
        # Count people per company
        people_count = {}
        if resp_jobs.data:
            for job in resp_jobs.data:
                cid = job["company_id"]
                people_count[cid] = people_count.get(cid, 0) + 1
        companies = [c for c in companies if people_count.get(c["id"], 0) < 3]
        logger.info("After skip-existing filter: %d companies", len(companies))

    if args.max > 0:
        companies = companies[:args.max]

    channels = (["website", "search", "conference"] if args.channel == "all"
                else [args.channel])

    logger.info("=" * 60)
    logger.info("People Research: %d companies, channels=%s, dry_run=%s",
                len(companies), channels, args.dry_run)
    logger.info("=" * 60)

    total_new = 0
    total_by_channel = {ch: 0 for ch in channels}
    now_str = datetime.now(timezone.utc).isoformat()

    # ── Per-company channels ──
    for i, company in enumerate(companies, 1):
        cid = company["id"]
        name = company["name"]
        website = company.get("website") or ""

        logger.info("\n[%d/%d] %s (%s)", i, len(companies), name, cid[:12])
        if website:
            logger.info("  Website: %s", website)

        company_progress = progress.get(cid, {})

        # Channel 1: Website
        if "website" in channels:
            if company_progress.get("website"):
                logger.info("  [SKIP] Website already processed on %s",
                            company_progress["website"][:10])
            elif not website:
                logger.info("  [SKIP] No website URL")
            else:
                logger.info("  --- Website scraping ---")
                people = discover_from_website(connector, fetcher, name, website)
                if people:
                    new, _ = persist_people(
                        client, persister, cid, name, people,
                        CONFIDENCE_WEBSITE, "website:" + website, args.dry_run,
                    )
                    total_new += new
                    total_by_channel["website"] = total_by_channel.get("website", 0) + new
                    logger.info("  Website: %d people found, %d persisted", len(people), new)
                else:
                    logger.info("  Website: no people found")

                if not args.dry_run:
                    company_progress["website"] = now_str

        # Channel 2: Search
        if "search" in channels:
            if company_progress.get("search"):
                logger.info("  [SKIP] Search already processed on %s",
                            company_progress["search"][:10])
            else:
                logger.info("  --- Perplexity search ---")
                time.sleep(0.5)
                people = discover_from_search(connector, name)
                if people:
                    new, _ = persist_people(
                        client, persister, cid, name, people,
                        CONFIDENCE_SEARCH, "perplexity search", args.dry_run,
                    )
                    total_new += new
                    total_by_channel["search"] = total_by_channel.get("search", 0) + new
                    logger.info("  Search: %d people found, %d persisted", len(people), new)
                else:
                    logger.info("  Search: no people found")

                if not args.dry_run:
                    company_progress["search"] = now_str

        # Save progress after each company
        if not args.dry_run:
            progress[cid] = company_progress
            save_progress(progress)

    # ── Conference channel (global, not per-company) ──
    if "conference" in channels:
        last_conf = progress.get("conference_last_run", "")
        # Skip if run within last 30 days
        skip_conference = False
        if last_conf:
            try:
                last_dt = datetime.fromisoformat(last_conf.replace("Z", "+00:00"))
                days_ago = (datetime.now(timezone.utc) - last_dt).days
                if days_ago < 30:
                    logger.info("\n[SKIP] Conference channel run %d days ago (< 30 days)", days_ago)
                    skip_conference = True
            except (ValueError, TypeError):
                pass

        if not skip_conference:
            logger.info("\n--- Conference speakers search ---")
            people = discover_from_conferences(connector)
            if people:
                # Deduplicate within batch by name
                seen_names = set()
                unique_people = []
                for p in people:
                    name_key = strip_accents((p.get("name") or "").strip().lower())
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        unique_people.append(p)

                logger.info("  Conference: %d unique speakers (from %d raw)",
                            len(unique_people), len(people))

                new = persist_conference_people(
                    client, persister, unique_people, args.dry_run,
                )
                total_new += new
                total_by_channel["conference"] = new
                logger.info("  Conference: %d persisted", new)
            else:
                logger.info("  Conference: no speakers found")

            if not args.dry_run:
                progress["conference_last_run"] = now_str
                save_progress(progress)

    # ── Summary ──
    logger.info("\n" + "=" * 60)
    logger.info("Done: %d new people total", total_new)
    for ch, count in total_by_channel.items():
        if count > 0:
            logger.info("  %s: %d", ch, count)
    if args.dry_run:
        logger.info("(DRY RUN — no changes were written)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

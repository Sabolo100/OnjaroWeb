"""Backfill the changes table from existing Supabase data.

The Postgres triggers that auto-log changes were not active when the bulk
data was loaded, so the changes table is nearly empty.  This script reads
all existing companies, buildings, people, jobs and building_management
records and creates a corresponding changes entry for each one.

Already-existing rows (by entity_id + change_type) are skipped, so the
script is safe to re-run multiple times.

Usage:
    source .env && export SUPABASE_URL SUPABASE_SERVICE_KEY
    python3 scripts/backfill_changes.py [--dry-run]
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")


def main():
    parser = argparse.ArgumentParser(description="Backfill changes table")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from research.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        logger.error("No Supabase client")
        sys.exit(1)

    # ── Load existing changes to avoid duplicates ──────────────────
    existing_resp = client.table("changes").select("entity_id,change_type").execute()
    existing = set()
    for r in (existing_resp.data or []):
        existing.add((r["entity_id"], r["change_type"]))
    logger.info("Existing changes rows: %d", len(existing))

    now = datetime.now(timezone.utc).isoformat()
    inserts = []

    # ── Companies ──────────────────────────────────────────────────
    resp = client.table("companies").select("id,name,confidence,created_at").execute()
    companies = {c["id"]: c["name"] for c in (resp.data or [])}
    for co in (resp.data or []):
        key = (co["id"], "new_entity")
        if key in existing:
            continue
        inserts.append({
            "change_type": "new_entity",
            "entity_type": "company",
            "entity_id": co["id"],
            "entity_name": co["name"],
            "summary": f"Új Cég: {co['name']}",
            "confidence": co.get("confidence") or 0.5,
            "source_urls": [],
            "created_at": co.get("created_at") or now,
        })
    logger.info("Companies to backfill: %d", sum(1 for x in inserts if x["entity_type"] == "company"))

    # ── Buildings ──────────────────────────────────────────────────
    resp = client.table("buildings").select("id,name,confidence,created_at").execute()
    buildings = {b["id"]: b["name"] for b in (resp.data or [])}
    before = len(inserts)
    for bldg in (resp.data or []):
        key = (bldg["id"], "new_entity")
        if key in existing:
            continue
        inserts.append({
            "change_type": "new_entity",
            "entity_type": "building",
            "entity_id": bldg["id"],
            "entity_name": bldg["name"],
            "summary": f"Új Ingatlan: {bldg['name']}",
            "confidence": bldg.get("confidence") or 0.5,
            "source_urls": [],
            "created_at": bldg.get("created_at") or now,
        })
    logger.info("Buildings to backfill: %d", len(inserts) - before)

    # ── People ─────────────────────────────────────────────────────
    resp = client.table("people").select("id,name,confidence,created_at").execute()
    people = {p["id"]: p["name"] for p in (resp.data or [])}
    before = len(inserts)
    for person in (resp.data or []):
        key = (person["id"], "new_entity")
        if key in existing:
            continue
        inserts.append({
            "change_type": "new_entity",
            "entity_type": "person",
            "entity_id": person["id"],
            "entity_name": person["name"],
            "summary": f"Új Szakmai szereplő: {person['name']}",
            "confidence": person.get("confidence") or 0.5,
            "source_urls": [],
            "created_at": person.get("created_at") or now,
        })
    logger.info("People to backfill: %d", len(inserts) - before)

    # ── Jobs (personnel moves) ─────────────────────────────────────
    resp = client.table("jobs").select("id,person_id,company_id,position_title,confidence,created_at").execute()
    before = len(inserts)
    for job in (resp.data or []):
        person_name = people.get(job["person_id"], "Ismeretlen")
        company_name = companies.get(job["company_id"], "Ismeretlen cég")
        key = (job["person_id"], "personnel_move")
        if key in existing:
            continue
        inserts.append({
            "change_type": "personnel_move",
            "entity_type": "person",
            "entity_id": job["person_id"],
            "entity_name": person_name,
            "summary": f"{person_name} → {job.get('position_title', 'Pozíció')} @ {company_name}",
            "related_entity_type": "company",
            "related_entity_id": job["company_id"],
            "related_entity_name": company_name,
            "confidence": job.get("confidence") or 0.5,
            "source_urls": [],
            "created_at": job.get("created_at") or now,
        })
    logger.info("Jobs (personnel_move) to backfill: %d", len(inserts) - before)

    # ── Building management ────────────────────────────────────────
    resp = client.table("building_management").select(
        "id,building_id,company_id,role,confidence,created_at"
    ).execute()
    before = len(inserts)
    for bm in (resp.data or []):
        building_name = buildings.get(bm["building_id"], "Ismeretlen épület")
        company_name = companies.get(bm["company_id"], "Ismeretlen cég")
        # Use building_id as entity_id so it's unique-ish per building
        key = (bm["building_id"] + "_" + bm["company_id"], "new_management")
        if key in existing:
            continue
        role = (bm.get("role") or "pm").upper()
        inserts.append({
            "change_type": "new_management",
            "entity_type": "building",
            "entity_id": bm["building_id"],
            "entity_name": building_name,
            "summary": f"{company_name} - {role} megbízás: {building_name}",
            "related_entity_type": "company",
            "related_entity_id": bm["company_id"],
            "related_entity_name": company_name,
            "confidence": bm.get("confidence") or 0.5,
            "source_urls": [],
            "created_at": bm.get("created_at") or now,
        })
    logger.info("Building management to backfill: %d", len(inserts) - before)

    # ── Insert ─────────────────────────────────────────────────────
    logger.info("Total rows to insert: %d", len(inserts))

    if args.dry_run:
        logger.info("[DRY RUN] Would insert %d rows into changes table", len(inserts))
        for r in inserts[:5]:
            logger.info("  %s %s: %s", r["change_type"], r["entity_type"], r["summary"][:60])
        return

    # Insert in batches of 100
    batch_size = 100
    total_inserted = 0
    for i in range(0, len(inserts), batch_size):
        batch = inserts[i:i + batch_size]
        try:
            client.table("changes").insert(batch).execute()
            total_inserted += len(batch)
            logger.info("Inserted batch %d-%d", i, i + len(batch))
        except Exception as e:
            logger.error("Batch insert failed at %d: %s", i, e)
            # Try one by one
            for row in batch:
                try:
                    client.table("changes").insert(row).execute()
                    total_inserted += 1
                except Exception as e2:
                    logger.warning("  Skip row %s: %s", row.get("entity_id", "?"), e2)

    logger.info("Done — inserted %d/%d rows", total_inserted, len(inserts))


if __name__ == "__main__":
    main()

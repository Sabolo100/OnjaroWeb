"""Geocode building addresses and store lat/lng in Supabase.

Uses Nominatim (OpenStreetMap) — free, no API key needed.
Rate limited to 1 request/second per OSM policy.

Usage:
    source .env && export SUPABASE_URL SUPABASE_SERVICE_KEY
    python3 scripts/geocode_buildings.py [--dry-run]
"""

import sys, os, time, argparse, logging, urllib.request, urllib.parse, json
from datetime import datetime, timezone
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "FMIntel/1.0 (fm-intel research; contact@fmintel.hu)"


def geocode(address: str, city: str) -> Optional[Tuple[float, float]]:
    """Query Nominatim for coordinates. Returns (lat, lon) or None."""
    # Build query: prefer full address, fall back to city only
    queries = []
    if address and len(address) > 5 and "hrsz" not in address.lower():
        # Clean address — strip zip prefix if it's part of city already
        full = f"{address}, {city}, Hungary" if city.lower() not in address.lower() else f"{address}, Hungary"
        queries.append(full)
    queries.append(f"{city}, Hungary")

    for q in queries:
        params = urllib.parse.urlencode({
            "q": q,
            "format": "json",
            "limit": 1,
            "countrycodes": "hu",
        })
        url = f"{NOMINATIM_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                logger.info("  ✓ %s → %.5f, %.5f", q[:60], lat, lon)
                return lat, lon
        except Exception as e:
            logger.warning("  Nominatim error for '%s': %s", q[:60], e)
        time.sleep(1.1)  # OSM rate limit

    return None


def main():
    parser = argparse.ArgumentParser(description="Geocode buildings")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--name", type=str, default=None, help="Filter by building name")
    args = parser.parse_args()

    from research.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        logger.error("No Supabase client")
        sys.exit(1)

    resp = client.table("buildings").select(
        "id,name,address,city,latitude,longitude"
    ).execute()
    buildings = resp.data or []

    # Only process those with address but no coords
    targets = [
        b for b in buildings
        if b.get("address") and not b.get("latitude")
    ]
    if args.name:
        targets = [b for b in targets if args.name.lower() in b["name"].lower()]

    logger.info("Buildings to geocode: %d / %d", len(targets), len(buildings))

    ok = 0
    fail = 0
    now = datetime.now(timezone.utc).isoformat()

    for i, b in enumerate(targets, 1):
        name = b["name"]
        address = b.get("address") or ""
        city = b.get("city") or "Budapest"
        logger.info("[%d/%d] %s | %s", i, len(targets), name, address[:50])

        result = geocode(address, city)
        if result:
            lat, lon = result
            if not args.dry_run:
                client.table("buildings").update({
                    "latitude": lat,
                    "longitude": lon,
                    "updated_at": now,
                }).eq("id", b["id"]).execute()
            ok += 1
        else:
            logger.warning("  ✗ Could not geocode: %s", name)
            fail += 1

        time.sleep(1.1)  # OSM rate limit

    logger.info("Done: %d geocoded, %d failed", ok, fail)


if __name__ == "__main__":
    main()

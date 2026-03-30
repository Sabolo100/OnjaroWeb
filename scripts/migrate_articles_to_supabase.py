#!/usr/bin/env python3
"""Migrate articles from webapp/src/data/articles.ts to Supabase.

Usage:
    # Run from project root:
    python3 scripts/migrate_articles_to_supabase.py

    # Dry run (print what would be migrated, no DB write):
    python3 scripts/migrate_articles_to_supabase.py --dry-run

    # Print CREATE TABLE SQL only:
    python3 scripts/migrate_articles_to_supabase.py --sql

Requires:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment
    - node available on PATH
    - pip install supabase
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# difficulty: TypeScript uses diacritics, Supabase schema uses ASCII
DIFFICULTY_MAP = {
    "kezdő": "kezdo",
    "középhaladó": "kozephalado",
    "haladó": "halado",
}


def load_env():
    """Load .env file from project root if present."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def extract_articles() -> list:
    """Run the Node.js extractor to get articles as Python dicts."""
    extractor = PROJECT_ROOT / "scripts" / "extract_articles.js"
    result = subprocess.run(
        ["node", str(extractor)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"ERROR running Node.js extractor:\n{result.stderr}")
        sys.exit(1)
    return json.loads(result.stdout)


def to_snake_case_row(article: dict) -> dict:
    """Convert camelCase Article dict to snake_case Supabase row."""
    key_map = {
        "id": "id",
        "type": "type",
        "style": "style",
        "category": "category",
        "title": "title",
        "excerpt": "excerpt",
        "wordCount": "word_count",
        "date": "date",
        "categoryColor": "category_color",
        "badge": "badge",
        "priceBadge": "price_badge",
        "featured": "featured",
        "recoveryTime": "recovery_time",
        "isNew": "is_new",
        "intensityZone": "intensity_zone",
        "ageBadge": "age_badge",
        "gearLevel": "gear_level",
        "content": "content",
        "weeksDuration": "weeks_duration",
        "sessionsPerWeek": "sessions_per_week",
        "difficulty": "difficulty",
    }
    row = {}
    for ts_key, db_key in key_map.items():
        if ts_key in article:
            value = article[ts_key]
            if ts_key == "difficulty" and value in DIFFICULTY_MAP:
                value = DIFFICULTY_MAP[value]
            row[db_key] = value
    return row


def create_table_sql() -> str:
    return """-- Run this in Supabase SQL Editor BEFORE migrating

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('cikk', 'edzesterv', 'felszereles')),
    style TEXT NOT NULL CHECK (style IN ('orszaguti', 'mtb', 'ciklokrossz', 'altalanos')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    word_count INTEGER,
    date DATE,
    category_color TEXT,
    badge JSONB,
    price_badge JSONB,
    featured BOOLEAN DEFAULT false,
    recovery_time JSONB,
    is_new BOOLEAN DEFAULT false,
    intensity_zone JSONB,
    age_badge JSONB,
    gear_level JSONB,
    content JSONB,
    weeks_duration INTEGER,
    sessions_per_week INTEGER,
    difficulty TEXT CHECK (difficulty IS NULL OR difficulty IN ('kezdo', 'kozephalado', 'halado')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read" ON articles FOR SELECT USING (true);
CREATE INDEX IF NOT EXISTS idx_articles_type ON articles(type);
CREATE INDEX IF NOT EXISTS idx_articles_style ON articles(style);
CREATE INDEX IF NOT EXISTS idx_articles_featured ON articles(featured) WHERE featured = true;
"""


def main():
    dry_run = "--dry-run" in sys.argv
    sql_only = "--sql" in sys.argv

    if sql_only:
        print(create_table_sql())
        return

    load_env()

    print("Extracting articles from articles.ts via Node.js...")
    raw_articles = extract_articles()
    print(f"Extracted {len(raw_articles)} articles")

    rows = [to_snake_case_row(a) for a in raw_articles]

    if dry_run:
        print("\n=== DRY RUN — would migrate ===")
        for r in rows:
            diff = f"  difficulty={r['difficulty']}" if r.get("difficulty") else ""
            print(f"  [{r.get('type')}] {r.get('id')}: {r.get('title', '')[:55]}{diff}")
        print(f"\nTotal: {len(rows)} articles")
        return

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env or environment")
        print("       Run with --sql to print the CREATE TABLE statement only")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: run: pip install supabase")
        sys.exit(1)

    client = create_client(url, key)
    print(f"Connected to {url}")
    print(f"Upserting {len(rows)} articles...")

    success = errors = 0
    for row in rows:
        try:
            client.table("articles").upsert(row).execute()
            success += 1
            print(f"  OK  {row['id']}: {row.get('title', '')[:55]}")
        except Exception as e:
            errors += 1
            print(f"  ERR {row['id']}: {e}")

    print(f"\nDone: {success} upserted, {errors} errors")


if __name__ == "__main__":
    main()

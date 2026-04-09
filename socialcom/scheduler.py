"""Socialcom scheduler — orchestrates the full detect → generate → publish pipeline.

Can be run as a standalone script or integrated into the orchestrator.
"""

import json
import logging
import sys
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from socialcom.config import MAX_PUBLISH_RETRIES, RETRY_DELAY_SECONDS
from socialcom.detector import detect_new_events
from socialcom.generator import generate_outputs
from socialcom.publishers.base import get_publisher

logger = logging.getLogger("socialcom.scheduler")


def _get_supabase():
    """Get Supabase client (reuses research module's singleton)."""
    try:
        from research.supabase_client import get_supabase_client
        return get_supabase_client()
    except ImportError:
        # Fallback: create our own client
        from socialcom.config import SUPABASE_URL, SUPABASE_SERVICE_KEY
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            logger.error("Supabase not configured")
            return None
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def publish_ready_outputs(client):
    # type: (Any) -> int
    """Publish all approved/scheduled outputs that are ready to go.
    Returns number of successfully published outputs."""

    # Fetch outputs ready for publishing:
    # - 'approved' = immediately publishable
    # - 'scheduled' with scheduled_at <= now
    now_iso = datetime.now(timezone.utc).isoformat()

    resp = client.table("comm_outputs").select(
        "*, channel:comm_channels(*)"
    ).in_("status", ["approved"]).order("created_at").limit(50).execute()

    outputs = resp.data or []

    # Also fetch scheduled outputs whose time has come
    sched_resp = client.table("comm_outputs").select(
        "*, channel:comm_channels(*)"
    ).eq("status", "scheduled").lte("scheduled_at", now_iso).order(
        "scheduled_at"
    ).limit(50).execute()

    outputs.extend(sched_resp.data or [])

    if not outputs:
        logger.info("No outputs ready for publishing")
        return 0

    logger.info("Publishing %d ready outputs", len(outputs))
    published = 0

    for output in outputs:
        output_id = output.get("id", "?")
        channel_info = output.get("channel")
        if not channel_info:
            logger.warning("  Output '%s' has no channel info — skip", output_id)
            continue

        channel_name = channel_info.get("channel_name", "")
        if not channel_info.get("is_enabled"):
            logger.info("  Channel '%s' disabled — marking output as skipped", channel_name)
            client.table("comm_outputs").update(
                {"status": "skipped", "updated_at": "now()"}
            ).eq("id", output_id).execute()
            continue

        publisher = get_publisher(channel_name)
        if not publisher:
            logger.warning("  No publisher for channel '%s'", channel_name)
            client.table("comm_outputs").update({
                "status": "failed",
                "error_message": "No publisher available for %s" % channel_name,
                "updated_at": "now()",
            }).eq("id", output_id).execute()
            continue

        if not publisher.validate_config():
            logger.warning("  Publisher '%s' not configured", channel_name)
            client.table("comm_outputs").update({
                "status": "failed",
                "error_message": "%s credentials not configured" % channel_name,
                "updated_at": "now()",
            }).eq("id", output_id).execute()
            continue

        # Mark as publishing
        client.table("comm_outputs").update(
            {"status": "publishing", "updated_at": "now()"}
        ).eq("id", output_id).execute()

        # Inject channel auth_config for publishers that need it (email recipients etc.)
        output["_channel_auth"] = channel_info.get("auth_config") or {}

        logger.info("  Publishing output '%s' to %s...", output_id, channel_name)
        result = publisher.publish(output)

        if result.success:
            client.table("comm_outputs").update({
                "status": "published",
                "published_at": "now()",
                "external_id": result.external_id or "",
                "updated_at": "now()",
            }).eq("id", output_id).execute()
            published += 1
            logger.info("    Published: %s → %s", output_id, result.external_id)
        else:
            retry_count = output.get("retry_count", 0) + 1
            new_status = "failed" if retry_count >= MAX_PUBLISH_RETRIES else "approved"
            client.table("comm_outputs").update({
                "status": new_status,
                "error_message": result.error or "Unknown error",
                "retry_count": retry_count,
                "updated_at": "now()",
            }).eq("id", output_id).execute()
            logger.error("    Failed (%d/%d): %s",
                         retry_count, MAX_PUBLISH_RETRIES, result.error)

    # Update parent events — if all outputs for an event are published, mark it
    _update_event_statuses(client)

    logger.info("Publishing done: %d/%d succeeded", published, len(outputs))
    return published


def _update_event_statuses(client):
    # type: (Any) -> None
    """Update comm_events status based on their outputs."""
    # Find events in 'ready' status
    resp = client.table("comm_events").select("id").eq("status", "ready").execute()
    for evt in (resp.data or []):
        eid = evt["id"]
        out_resp = client.table("comm_outputs").select(
            "status"
        ).eq("event_id", eid).execute()
        statuses = [o["status"] for o in (out_resp.data or [])]

        if not statuses:
            continue

        all_final = all(s in ("published", "failed", "skipped") for s in statuses)
        if not all_final:
            continue

        if all(s == "published" for s in statuses):
            new_status = "published"
        elif any(s == "published" for s in statuses):
            new_status = "partial"
        else:
            new_status = "failed"

        client.table("comm_events").update(
            {"status": new_status, "updated_at": "now()"}
        ).eq("id", eid).execute()


def run_pipeline(dry_run=False):
    # type: (bool) -> Dict[str, Any]
    """Run the full socialcom pipeline: detect → generate → publish.

    Returns a summary dict with counts.
    """
    client = _get_supabase()
    if not client:
        logger.error("Cannot run pipeline — no Supabase client")
        return {"error": "No database connection"}

    logger.info("=" * 60)
    logger.info("SOCIALCOM PIPELINE START")
    logger.info("=" * 60)

    # Phase 1: Detect new communicable events
    logger.info("\n── Phase 1: Detecting new events ──")
    new_events = detect_new_events(client)

    # Phase 2: Generate content for pending events
    logger.info("\n── Phase 2: Generating content ──")
    new_outputs = generate_outputs(client)

    # Phase 3: Publish approved outputs
    published_count = 0
    if not dry_run:
        logger.info("\n── Phase 3: Publishing ──")
        published_count = publish_ready_outputs(client)
    else:
        logger.info("\n── Phase 3: Publishing (DRY RUN — skipped) ──")

    summary = {
        "events_detected": len(new_events),
        "outputs_generated": len(new_outputs),
        "outputs_published": published_count,
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("\n" + "=" * 60)
    logger.info("SOCIALCOM PIPELINE DONE: %s", json.dumps(summary))
    logger.info("=" * 60)

    return summary


def get_pipeline_status(client=None):
    # type: (Any) -> Dict[str, Any]
    """Get current pipeline status for the dashboard."""
    if not client:
        client = _get_supabase()
    if not client:
        return {"error": "No database connection"}

    try:
        # Event counts by status
        events_resp = client.table("comm_events").select(
            "status", count="exact"
        ).execute()
        events = events_resp.data or []
        event_counts = {}
        for e in events:
            s = e.get("status", "unknown")
            event_counts[s] = event_counts.get(s, 0) + 1

        # Output counts by status
        outputs_resp = client.table("comm_outputs").select(
            "status", count="exact"
        ).execute()
        outputs = outputs_resp.data or []
        output_counts = {}
        for o in outputs:
            s = o.get("status", "unknown")
            output_counts[s] = output_counts.get(s, 0) + 1

        # Channel health
        ch_resp = client.table("comm_channels").select("*").execute()
        channels = []
        for ch in (ch_resp.data or []):
            channels.append({
                "name": ch.get("channel_name"),
                "display_name": ch.get("display_name"),
                "enabled": ch.get("is_enabled", False),
                "mode": ch.get("default_mode", "draft"),
                "auth_status": ch.get("auth_status", "not_configured"),
            })

        # Recent outputs
        recent_resp = client.table("comm_outputs").select(
            "id, title, status, published_at, created_at, "
            "channel:comm_channels(channel_name, display_name), "
            "event:comm_events(title, event_type)"
        ).order("created_at", desc=True).limit(20).execute()

        return {
            "event_counts": event_counts,
            "output_counts": output_counts,
            "channels": channels,
            "recent_outputs": recent_resp.data or [],
            "total_events": len(events),
            "total_outputs": len(outputs),
        }
    except Exception as e:
        logger.error("Failed to get pipeline status: %s", e)
        return {"error": str(e)}


# ── CLI entry point ─────────────────────────────────────────────────

def main():
    """CLI entry point for manual runs."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Socialcom — Communication Pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and generate but don't publish")
    parser.add_argument("--detect-only", action="store_true",
                        help="Only run the detection phase")
    parser.add_argument("--generate-only", action="store_true",
                        help="Only run the generation phase")
    parser.add_argument("--publish-only", action="store_true",
                        help="Only publish approved outputs")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status and exit")
    args = parser.parse_args()

    client = _get_supabase()
    if not client:
        logger.error("No Supabase client — check SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    if args.status:
        status = get_pipeline_status(client)
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if args.detect_only:
        events = detect_new_events(client)
        print("Detected %d new events" % len(events))
        return

    if args.generate_only:
        outputs = generate_outputs(client)
        print("Generated %d outputs" % len(outputs))
        return

    if args.publish_only:
        count = publish_ready_outputs(client)
        print("Published %d outputs" % count)
        return

    # Full pipeline
    summary = run_pipeline(dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Change detector — scans the `changes` table for communicable events.

Reads new entries from the `changes` table since the last processed ID,
classifies each change's communication worthiness, and creates
`comm_events` records for those worth communicating.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from socialcom.config import PROGRESS_FILE

logger = logging.getLogger("socialcom.detector")

# ── Event type mapping ──────────────────────────────────────────────

# Map change_type → comm event_type
_CHANGE_TYPE_MAP = {
    "new_entity": "new_entity",
    "updated_entity": "data_update",
    "new_management": "new_entity",
    "ended_management": "data_update",
    "personnel_move": "new_entity",
    "company_relation": "data_update",
    "data_correction": "data_update",
}

# Priority based on change_type
_PRIORITY_MAP = {
    "new_entity": "medium",
    "new_management": "medium",
    "personnel_move": "medium",
    "updated_entity": "low",
    "ended_management": "low",
    "company_relation": "low",
    "data_correction": "low",
}

# Minimum confidence to be considered communicable
MIN_CONFIDENCE = 0.6


def _load_last_processed_id():
    # type: () -> int
    """Load the last processed change ID from progress file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_change_id", 0)
        except (json.JSONDecodeError, IOError):
            pass
    return 0


def _save_last_processed_id(change_id):
    # type: (int) -> None
    """Save the last processed change ID to progress file."""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    data = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    data["last_change_id"] = change_id
    data["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _is_communicable(change):
    # type: (Dict[str, Any]) -> bool
    """Determine if a change is worth communicating."""
    # Skip low-confidence changes
    confidence = change.get("confidence", 0)
    if confidence < MIN_CONFIDENCE:
        return False

    # Skip data corrections — they're internal housekeeping
    if change.get("change_type") == "data_correction":
        return False

    # Must have a summary
    if not change.get("summary"):
        return False

    return True


def _classify_priority(change):
    # type: (Dict[str, Any]) -> str
    """Determine communication priority."""
    change_type = change.get("change_type", "")
    priority = _PRIORITY_MAP.get(change_type, "low")

    # Boost priority for high-confidence entities
    confidence = change.get("confidence", 0)
    if confidence >= 0.85 and priority == "low":
        priority = "medium"

    return priority


def _determine_channels(change, priority):
    # type: (Dict[str, Any], str) -> List[str]
    """Determine which channels a change should be published to."""
    channels = []

    if priority == "high":
        channels = ["linkedin", "mailchimp", "facebook", "email"]
    elif priority == "medium":
        channels = ["linkedin", "facebook"]
    else:
        # Low priority — only digest / aggregation later
        channels = ["mailchimp"]

    return channels


def _build_event_title(change):
    # type: (Dict[str, Any]) -> str
    """Build a human-readable title for the comm event."""
    summary = change.get("summary", "")
    entity_name = change.get("entity_name", "")
    change_type = change.get("change_type", "")

    if change_type == "new_entity":
        return "Új adat: %s" % (entity_name or summary)
    elif change_type == "new_management":
        return "Új megbízás: %s" % summary
    elif change_type == "personnel_move":
        return "Személyi változás: %s" % summary
    elif change_type == "updated_entity":
        return "Frissítés: %s" % (entity_name or summary)
    else:
        return summary or "Platform frissítés"


def detect_new_events(client):
    # type: (Any) -> List[Dict[str, Any]]
    """Scan changes table for new communicable events. Returns list of created comm_events."""
    last_id = _load_last_processed_id()

    # Fetch new changes since last run
    resp = client.table("changes").select("*").gt("id", last_id).order(
        "id", desc=False
    ).limit(200).execute()
    changes = resp.data or []

    if not changes:
        logger.info("No new changes since id=%d", last_id)
        return []

    logger.info("Found %d new changes (id > %d)", len(changes), last_id)

    created_events = []
    max_id = last_id

    for change in changes:
        cid = change.get("id", 0)
        if cid > max_id:
            max_id = cid

        if not _is_communicable(change):
            logger.debug("  Skip change #%d — not communicable", cid)
            continue

        # Check if we already have a comm_event for this change
        existing = client.table("comm_events").select("id").eq(
            "change_id", cid
        ).execute()
        if existing.data:
            logger.debug("  Skip change #%d — already has comm_event", cid)
            continue

        priority = _classify_priority(change)
        channels = _determine_channels(change, priority)
        title = _build_event_title(change)
        event_type = _CHANGE_TYPE_MAP.get(change.get("change_type", ""), "data_update")

        payload = {
            "entity_type": change.get("entity_type"),
            "entity_id": change.get("entity_id"),
            "entity_name": change.get("entity_name"),
            "change_type": change.get("change_type"),
            "related_entity_type": change.get("related_entity_type"),
            "related_entity_name": change.get("related_entity_name"),
            "details": change.get("details"),
        }

        event_data = {
            "change_id": cid,
            "event_type": event_type,
            "title": title,
            "summary": change.get("summary", ""),
            "priority": priority,
            "target_channels": channels,
            "payload": json.dumps(payload, ensure_ascii=False),
            "status": "pending",
        }

        try:
            result = client.table("comm_events").insert(event_data).execute()
            if result.data:
                evt = result.data[0]
                created_events.append(evt)
                logger.info("  Created comm_event '%s' for change #%d → %s",
                            evt.get("id", "?"), cid, channels)
        except Exception as e:
            logger.error("  Failed to create comm_event for change #%d: %s", cid, e)

    # Save progress
    _save_last_processed_id(max_id)
    logger.info("Detector done: %d events created, last_id=%d", len(created_events), max_id)
    return created_events

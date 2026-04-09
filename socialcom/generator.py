"""Content generator — creates channel-specific content for comm_events.

Takes pending comm_events and generates per-channel outputs using
AI (Perplexity API) with channel-specific prompts.
"""

import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

from socialcom.config import PERPLEXITY_API_KEY, PERPLEXITY_MODEL
from socialcom.prompts import CHANNEL_PROMPTS, SYSTEM_PROMPT

logger = logging.getLogger("socialcom.generator")

# ── AI client ───────────────────────────────────────────────────────

_ai_client = None


def _get_ai_client():
    """Get or create the OpenAI-compatible Perplexity client."""
    global _ai_client
    if _ai_client is not None:
        return _ai_client

    if not PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY not set — cannot generate content")
        return None

    try:
        from openai import OpenAI
        _ai_client = OpenAI(
            api_key=PERPLEXITY_API_KEY,
            base_url="https://api.perplexity.ai",
        )
        return _ai_client
    except ImportError:
        logger.error("openai package required: pip install openai")
        return None


def _parse_json_response(text):
    # type: (str) -> Dict[str, Any]
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


def _generate_for_channel(event, channel_name, channel_tone):
    # type: (Dict[str, Any], str, str) -> Optional[Dict[str, Any]]
    """Generate content for a single channel using AI."""
    client = _get_ai_client()
    if not client:
        return None

    prompt_template = CHANNEL_PROMPTS.get(channel_name)
    if not prompt_template:
        logger.warning("No prompt template for channel '%s'", channel_name)
        return None

    # Build event details string
    payload = event.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    elif payload is None:
        payload = {}

    details_str = json.dumps(payload, ensure_ascii=False, indent=2)

    # Map event_type to human-readable Hungarian
    event_type_labels = {
        "new_entity": "Új entitás az adatbázisban",
        "data_update": "Adatfrissítés",
        "feature_launch": "Új funkció",
        "milestone": "Mérföldkő",
        "weekly_digest": "Heti összefoglaló",
        "monthly_digest": "Havi összefoglaló",
        "data_enrichment": "Adatbővítés",
    }
    event_type_label = event_type_labels.get(event.get("event_type", ""), "Frissítés")

    prompt = prompt_template.format(
        event_type=event_type_label,
        title=event.get("title", ""),
        summary=event.get("summary", ""),
        details=details_str[:3000],  # Limit detail length
        channel_tone=channel_tone or "",
    )

    try:
        response = client.chat.completions.create(
            model=PERPLEXITY_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        resp_text = response.choices[0].message.content if response.choices else ""
        data = _parse_json_response(resp_text)

        if not data.get("body"):
            logger.warning("AI returned empty body for event '%s' on %s",
                           event.get("id", "?"), channel_name)
            return None

        return {
            "title": data.get("title", ""),
            "body": data.get("body", ""),
            "cta": data.get("cta", ""),
            "hashtags": data.get("hashtags", []),
        }
    except Exception as e:
        logger.error("AI generation failed for %s on %s: %s",
                      event.get("id", "?"), channel_name, e)
        return None


def generate_outputs(client):
    # type: (Any) -> List[Dict[str, Any]]
    """Generate content for all pending comm_events. Returns created comm_outputs."""

    # Fetch pending events
    resp = client.table("comm_events").select("*").eq(
        "status", "pending"
    ).order("created_at").limit(50).execute()
    events = resp.data or []

    if not events:
        logger.info("No pending comm_events to generate")
        return []

    # Fetch enabled channels
    ch_resp = client.table("comm_channels").select("*").eq(
        "is_enabled", True
    ).execute()
    channels_by_name = {}
    for ch in (ch_resp.data or []):
        channels_by_name[ch["channel_name"]] = ch

    if not channels_by_name:
        logger.info("No enabled channels — skipping generation")
        return []

    logger.info("Generating content for %d events across %d enabled channels",
                len(events), len(channels_by_name))

    all_outputs = []

    for event in events:
        event_id = event.get("id", "?")
        target_channels = event.get("target_channels", [])
        if not target_channels:
            target_channels = list(channels_by_name.keys())

        # Mark event as generating
        try:
            client.table("comm_events").update(
                {"status": "generating"}
            ).eq("id", event_id).execute()
        except Exception:
            pass

        event_outputs = []
        for ch_name in target_channels:
            ch_config = channels_by_name.get(ch_name)
            if not ch_config:
                logger.debug("  Channel '%s' not enabled — skip", ch_name)
                continue

            logger.info("  Generating %s content for event '%s'", ch_name, event_id)
            time.sleep(0.5)  # Rate limit

            content = _generate_for_channel(
                event, ch_name, ch_config.get("tone", "")
            )

            if not content:
                logger.warning("  No content generated for %s / %s", event_id, ch_name)
                continue

            # Determine initial status based on channel mode
            mode = ch_config.get("default_mode", "draft")
            if mode == "auto":
                initial_status = "approved"
            elif mode == "approval":
                initial_status = "pending_approval"
            else:
                initial_status = "draft"

            output_data = {
                "event_id": event_id,
                "channel_id": ch_config["id"],
                "title": content.get("title", ""),
                "body": content.get("body", ""),
                "cta": content.get("cta", ""),
                "hashtags": content.get("hashtags", []),
                "status": initial_status,
            }

            try:
                result = client.table("comm_outputs").insert(output_data).execute()
                if result.data:
                    out = result.data[0]
                    event_outputs.append(out)
                    logger.info("    Created output '%s' [%s] → %s",
                                out.get("id", "?"), ch_name, initial_status)
            except Exception as e:
                logger.error("    Failed to create output for %s/%s: %s",
                             event_id, ch_name, e)

        # Update event status
        if event_outputs:
            new_status = "ready"
        else:
            new_status = "failed"

        try:
            client.table("comm_events").update(
                {"status": new_status, "updated_at": "now()"}
            ).eq("id", event_id).execute()
        except Exception:
            pass

        all_outputs.extend(event_outputs)

    logger.info("Generator done: %d outputs created", len(all_outputs))
    return all_outputs

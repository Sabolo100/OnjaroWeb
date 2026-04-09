"""Facebook publisher — posts to a Facebook Page via Graph API.

Requires:
- FACEBOOK_PAGE_ACCESS_TOKEN: Page access token with pages_manage_posts permission
- FACEBOOK_PAGE_ID: Facebook Page ID

API docs: https://developers.facebook.com/docs/pages-api/posts
"""

import logging
from typing import Dict, Any

import requests

from socialcom.config import FACEBOOK_PAGE_ACCESS_TOKEN, FACEBOOK_PAGE_ID
from socialcom.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger("socialcom.publishers.facebook")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class FacebookPublisher(BasePublisher):
    channel_name = "facebook"

    def validate_config(self):
        # type: () -> bool
        if not FACEBOOK_PAGE_ACCESS_TOKEN:
            logger.warning("FACEBOOK_PAGE_ACCESS_TOKEN not configured")
            return False
        if not FACEBOOK_PAGE_ID:
            logger.warning("FACEBOOK_PAGE_ID not configured")
            return False
        return True

    def format_content(self, output):
        # type: (Dict[str, Any]) -> str
        """Format for Facebook — body + hashtags."""
        parts = []
        if output.get("body"):
            parts.append(output["body"])
        if output.get("cta"):
            parts.append(output["cta"])
        if output.get("hashtags"):
            tags = output["hashtags"]
            if isinstance(tags, list):
                parts.append(" ".join("#%s" % t for t in tags))
        return "\n\n".join(parts)

    def publish(self, output):
        # type: (Dict[str, Any]) -> PublishResult
        if not self.validate_config():
            return PublishResult(False, error="Facebook not configured")

        text = self.format_content(output)

        try:
            resp = requests.post(
                "%s/%s/feed" % (GRAPH_API_BASE, FACEBOOK_PAGE_ID),
                data={
                    "message": text,
                    "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                },
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                post_id = data.get("id", "")
                logger.info("Facebook post published: %s", post_id)
                return PublishResult(True, external_id=post_id)
            else:
                error_msg = "HTTP %d: %s" % (resp.status_code, resp.text[:500])
                logger.error("Facebook publish failed: %s", error_msg)
                return PublishResult(False, error=error_msg)

        except requests.RequestException as e:
            error_msg = "Request failed: %s" % str(e)
            logger.error("Facebook publish error: %s", error_msg)
            return PublishResult(False, error=error_msg)

    def health_check(self):
        # type: () -> bool
        if not self.validate_config():
            return False
        try:
            resp = requests.get(
                "%s/%s" % (GRAPH_API_BASE, FACEBOOK_PAGE_ID),
                params={"access_token": FACEBOOK_PAGE_ACCESS_TOKEN, "fields": "id"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

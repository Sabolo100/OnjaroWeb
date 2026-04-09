"""LinkedIn publisher — posts to LinkedIn via the Community Management API.

Requires:
- LINKEDIN_ACCESS_TOKEN: OAuth2 access token with w_member_social or w_organization_social scope
- LINKEDIN_ORG_ID: (optional) Organization URN for company page posts

API docs: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
"""

import json
import logging
from typing import Dict, Any

import requests

from socialcom.config import LINKEDIN_ACCESS_TOKEN, LINKEDIN_ORG_ID
from socialcom.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger("socialcom.publishers.linkedin")

LINKEDIN_API_BASE = "https://api.linkedin.com/rest"


class LinkedInPublisher(BasePublisher):
    channel_name = "linkedin"

    def validate_config(self):
        # type: () -> bool
        if not LINKEDIN_ACCESS_TOKEN:
            logger.warning("LINKEDIN_ACCESS_TOKEN not configured")
            return False
        return True

    def _get_author_urn(self):
        # type: () -> str
        """Get the author URN — org page if configured, else personal profile."""
        if LINKEDIN_ORG_ID:
            return "urn:li:organization:%s" % LINKEDIN_ORG_ID

        # Fetch own profile URN
        try:
            resp = requests.get(
                "%s/me" % LINKEDIN_API_BASE,
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return "urn:li:person:%s" % data.get("id", "")
        except Exception as e:
            logger.error("Failed to fetch LinkedIn profile: %s", e)
            return ""

    def _headers(self):
        return {
            "Authorization": "Bearer %s" % LINKEDIN_ACCESS_TOKEN,
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        }

    def format_content(self, output):
        # type: (Dict[str, Any]) -> str
        """Format for LinkedIn — body + hashtags, no title duplication."""
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
            return PublishResult(False, error="LinkedIn not configured")

        author = self._get_author_urn()
        if not author:
            return PublishResult(False, error="Could not determine LinkedIn author URN")

        text = self.format_content(output)

        post_data = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "visibility": "PUBLIC",
            "commentary": text,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
            },
        }

        try:
            resp = requests.post(
                "%s/posts" % LINKEDIN_API_BASE,
                headers=self._headers(),
                json=post_data,
                timeout=30,
            )

            if resp.status_code in (200, 201):
                # LinkedIn returns the post URN in the x-restli-id header
                post_id = resp.headers.get("x-restli-id", "")
                logger.info("LinkedIn post published: %s", post_id)
                return PublishResult(True, external_id=post_id)
            else:
                error_msg = "HTTP %d: %s" % (resp.status_code, resp.text[:500])
                logger.error("LinkedIn publish failed: %s", error_msg)
                return PublishResult(False, error=error_msg)

        except requests.RequestException as e:
            error_msg = "Request failed: %s" % str(e)
            logger.error("LinkedIn publish error: %s", error_msg)
            return PublishResult(False, error=error_msg)

    def health_check(self):
        # type: () -> bool
        if not LINKEDIN_ACCESS_TOKEN:
            return False
        try:
            resp = requests.get(
                "%s/me" % LINKEDIN_API_BASE,
                headers=self._headers(),
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

"""Mailchimp publisher — creates and sends email campaigns via the Mailchimp API.

Requires:
- MAILCHIMP_API_KEY: API key (ends with -usXX where XX is the server prefix)
- MAILCHIMP_SERVER_PREFIX: Data center prefix (e.g. us21)
- MAILCHIMP_LIST_ID: Audience/list ID to send to
- MAILCHIMP_FROM_NAME: Sender name
- MAILCHIMP_FROM_EMAIL: Sender email (verified in Mailchimp)

API docs: https://mailchimp.com/developer/marketing/api/campaigns/
"""

import json
import logging
from typing import Dict, Any

import requests

from socialcom.config import (
    MAILCHIMP_API_KEY,
    MAILCHIMP_SERVER_PREFIX,
    MAILCHIMP_LIST_ID,
    MAILCHIMP_FROM_NAME,
    MAILCHIMP_FROM_EMAIL,
)
from socialcom.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger("socialcom.publishers.mailchimp")


class MailchimpPublisher(BasePublisher):
    channel_name = "mailchimp"

    def _api_base(self):
        return "https://%s.api.mailchimp.com/3.0" % MAILCHIMP_SERVER_PREFIX

    def _auth(self):
        return ("anystring", MAILCHIMP_API_KEY)

    def validate_config(self):
        # type: () -> bool
        missing = []
        if not MAILCHIMP_API_KEY:
            missing.append("MAILCHIMP_API_KEY")
        if not MAILCHIMP_SERVER_PREFIX:
            missing.append("MAILCHIMP_SERVER_PREFIX")
        if not MAILCHIMP_LIST_ID:
            missing.append("MAILCHIMP_LIST_ID")
        if not MAILCHIMP_FROM_EMAIL:
            missing.append("MAILCHIMP_FROM_EMAIL")
        if missing:
            logger.warning("Mailchimp missing config: %s", ", ".join(missing))
            return False
        return True

    def _create_campaign(self, subject, preview_text=""):
        # type: (str, str) -> str | None
        """Create a new regular campaign. Returns campaign ID."""
        data = {
            "type": "regular",
            "recipients": {
                "list_id": MAILCHIMP_LIST_ID,
            },
            "settings": {
                "subject_line": subject,
                "preview_text": preview_text[:150] if preview_text else "",
                "from_name": MAILCHIMP_FROM_NAME,
                "reply_to": MAILCHIMP_FROM_EMAIL,
            },
        }

        try:
            resp = requests.post(
                "%s/campaigns" % self._api_base(),
                auth=self._auth(),
                json=data,
                timeout=30,
            )
            resp.raise_for_status()
            campaign = resp.json()
            return campaign.get("id")
        except Exception as e:
            logger.error("Failed to create Mailchimp campaign: %s", e)
            return None

    def _set_campaign_content(self, campaign_id, html_content):
        # type: (str, str) -> bool
        """Set the HTML content for a campaign."""
        try:
            resp = requests.put(
                "%s/campaigns/%s/content" % (self._api_base(), campaign_id),
                auth=self._auth(),
                json={"html": html_content},
                timeout=30,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Failed to set campaign content: %s", e)
            return False

    def _send_campaign(self, campaign_id):
        # type: (str) -> bool
        """Send the campaign."""
        try:
            resp = requests.post(
                "%s/campaigns/%s/actions/send" % (self._api_base(), campaign_id),
                auth=self._auth(),
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return True
            logger.error("Mailchimp send failed: HTTP %d %s",
                         resp.status_code, resp.text[:300])
            return False
        except Exception as e:
            logger.error("Failed to send Mailchimp campaign: %s", e)
            return False

    def _build_html(self, output):
        # type: (Dict[str, Any]) -> str
        """Build simple HTML email from output fields."""
        title = output.get("title", "FMintel frissítés")
        body = output.get("body", "")
        cta = output.get("cta", "")

        # Convert newlines to <br>
        body_html = body.replace("\n", "<br>")

        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
  <div style="background: #0284c7; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
    <h1 style="margin: 0; font-size: 22px;">FMintel</h1>
    <p style="margin: 4px 0 0; opacity: 0.9; font-size: 13px;">Piaci Intelligencia Platform</p>
  </div>
  <div style="background: white; padding: 24px; border: 1px solid #e2e8f0; border-top: none;">
    <h2 style="color: #0f172a; font-size: 18px; margin-top: 0;">{title}</h2>
    <div style="font-size: 15px; line-height: 1.6; color: #475569;">{body}</div>
    {cta_block}
  </div>
  <div style="padding: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
    FMintel — Magyar Ingatlanpiaci Intelligencia
  </div>
</body>
</html>""".format(
            title=title,
            body=body_html,
            cta_block=(
                '<div style="text-align: center; margin-top: 24px;">'
                '<a href="https://fmintel.hu" style="background: #0284c7; color: white; '
                'padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: bold;">'
                '%s</a></div>' % cta
            ) if cta else "",
        )
        return html

    def publish(self, output):
        # type: (Dict[str, Any]) -> PublishResult
        if not self.validate_config():
            return PublishResult(False, error="Mailchimp not configured")

        subject = output.get("title", "FMintel frissítés")

        # 1. Create campaign
        campaign_id = self._create_campaign(subject, output.get("body", "")[:150])
        if not campaign_id:
            return PublishResult(False, error="Failed to create campaign")

        # 2. Set content
        html = self._build_html(output)
        if not self._set_campaign_content(campaign_id, html):
            return PublishResult(False, error="Failed to set campaign content")

        # 3. Send
        if self._send_campaign(campaign_id):
            logger.info("Mailchimp campaign sent: %s", campaign_id)
            return PublishResult(True, external_id=campaign_id)
        else:
            return PublishResult(False, error="Failed to send campaign %s" % campaign_id)

    def health_check(self):
        # type: () -> bool
        if not self.validate_config():
            return False
        try:
            resp = requests.get(
                "%s/ping" % self._api_base(),
                auth=self._auth(),
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

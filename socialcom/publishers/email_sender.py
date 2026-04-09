"""Email publisher — sends emails via SMTP.

Requires:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
- SMTP_FROM_EMAIL, SMTP_FROM_NAME

Sends to a configured recipient list (stored in channel auth_config).
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List

from socialcom.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM_EMAIL, SMTP_FROM_NAME,
)
from socialcom.publishers.base import BasePublisher, PublishResult

logger = logging.getLogger("socialcom.publishers.email")


class EmailPublisher(BasePublisher):
    channel_name = "email"

    def validate_config(self):
        # type: () -> bool
        missing = []
        if not SMTP_HOST:
            missing.append("SMTP_HOST")
        if not SMTP_FROM_EMAIL:
            missing.append("SMTP_FROM_EMAIL")
        if missing:
            logger.warning("Email missing config: %s", ", ".join(missing))
            return False
        return True

    def _get_recipients(self, output):
        # type: (Dict[str, Any]) -> List[str]
        """Get recipient list from output assets or channel config."""
        # Check if recipients specified in output assets
        assets = output.get("assets") or {}
        if isinstance(assets, str):
            import json
            try:
                assets = json.loads(assets)
            except (ValueError, TypeError):
                assets = {}
        recipients = assets.get("recipients", [])
        if recipients:
            return recipients

        # Fallback: check channel auth_config (stored in DB)
        # The scheduler should inject this from comm_channels.auth_config
        auth = output.get("_channel_auth", {})
        return auth.get("recipients", [])

    def _build_html(self, output):
        # type: (Dict[str, Any]) -> str
        """Build simple HTML email body."""
        body = output.get("body", "")
        cta = output.get("cta", "")
        body_html = body.replace("\n", "<br>")

        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
  <div style="font-size: 15px; line-height: 1.6;">{body}</div>
  {cta_block}
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
  <p style="font-size: 12px; color: #94a3b8;">FMintel — Piaci Intelligencia Platform</p>
</body>
</html>""".format(
            body=body_html,
            cta_block=(
                '<p><a href="https://fmintel.hu" style="color: #0284c7; font-weight: bold;">%s</a></p>' % cta
            ) if cta else "",
        )
        return html

    def publish(self, output):
        # type: (Dict[str, Any]) -> PublishResult
        if not self.validate_config():
            return PublishResult(False, error="Email SMTP not configured")

        recipients = self._get_recipients(output)
        if not recipients:
            return PublishResult(False, error="No email recipients configured")

        subject = output.get("title", "FMintel frissítés")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = "%s <%s>" % (SMTP_FROM_NAME, SMTP_FROM_EMAIL)
        msg["To"] = ", ".join(recipients)

        # Plain text version
        plain = output.get("body", "")
        if output.get("cta"):
            plain += "\n\n%s\nhttps://fmintel.hu" % output["cta"]
        msg.attach(MIMEText(plain, "plain", "utf-8"))

        # HTML version
        html = self._build_html(output)
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
                server.starttls()

            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)

            server.sendmail(SMTP_FROM_EMAIL, recipients, msg.as_string())
            server.quit()

            logger.info("Email sent to %d recipients: %s", len(recipients), subject)
            return PublishResult(True, external_id="email:%d" % len(recipients))

        except Exception as e:
            error_msg = "SMTP error: %s" % str(e)
            logger.error("Email send failed: %s", error_msg)
            return PublishResult(False, error=error_msg)

    def health_check(self):
        # type: () -> bool
        if not self.validate_config():
            return False
        try:
            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.quit()
            return True
        except Exception:
            return False

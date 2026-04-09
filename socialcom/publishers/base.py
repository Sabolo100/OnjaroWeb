"""Base publisher interface — all channel publishers inherit from this."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("socialcom.publishers")


class PublishResult:
    """Result of a publish attempt."""

    def __init__(self, success, external_id=None, error=None):
        # type: (bool, Optional[str], Optional[str]) -> None
        self.success = success
        self.external_id = external_id
        self.error = error

    def __repr__(self):
        if self.success:
            return "PublishResult(ok, id=%s)" % self.external_id
        return "PublishResult(FAIL, error=%s)" % self.error


class BasePublisher:
    """Abstract base class for all channel publishers.

    To add a new channel:
    1. Create a new file in socialcom/publishers/
    2. Subclass BasePublisher
    3. Implement validate_config(), publish(), health_check()
    4. Register in PUBLISHER_REGISTRY below
    """

    channel_name = None  # Override in subclass

    def validate_config(self):
        # type: () -> bool
        """Check if all required config/credentials are present.
        Returns True if the publisher is ready to use."""
        raise NotImplementedError

    def publish(self, output):
        # type: (Dict[str, Any]) -> PublishResult
        """Publish a comm_output to the external platform.

        Args:
            output: dict with keys: title, body, cta, hashtags, assets

        Returns:
            PublishResult with success status and external ID or error
        """
        raise NotImplementedError

    def health_check(self):
        # type: () -> bool
        """Quick check if the channel connection is alive."""
        return self.validate_config()

    def format_content(self, output):
        # type: (Dict[str, Any]) -> str
        """Format the output into the final publishable text.
        Override in subclass for channel-specific formatting."""
        parts = []
        if output.get("title"):
            parts.append(output["title"])
        if output.get("body"):
            parts.append(output["body"])
        if output.get("cta"):
            parts.append(output["cta"])
        if output.get("hashtags"):
            tags = output["hashtags"]
            if isinstance(tags, list):
                parts.append(" ".join("#%s" % t for t in tags))
        return "\n\n".join(parts)


def get_publisher(channel_name):
    # type: (str) -> Optional[BasePublisher]
    """Get a publisher instance by channel name."""
    cls = PUBLISHER_REGISTRY.get(channel_name)
    if cls:
        return cls()
    return None


# ── Registry — populated at import time ─────────────────────────────
# Lazy import to avoid circular deps and allow partial installs

PUBLISHER_REGISTRY = {}


def _register_publishers():
    """Register available publishers."""
    try:
        from socialcom.publishers.linkedin import LinkedInPublisher
        PUBLISHER_REGISTRY["linkedin"] = LinkedInPublisher
    except ImportError:
        pass

    try:
        from socialcom.publishers.mailchimp_pub import MailchimpPublisher
        PUBLISHER_REGISTRY["mailchimp"] = MailchimpPublisher
    except ImportError:
        pass

    try:
        from socialcom.publishers.email_sender import EmailPublisher
        PUBLISHER_REGISTRY["email"] = EmailPublisher
    except ImportError:
        pass

    try:
        from socialcom.publishers.facebook import FacebookPublisher
        PUBLISHER_REGISTRY["facebook"] = FacebookPublisher
    except ImportError:
        pass


_register_publishers()

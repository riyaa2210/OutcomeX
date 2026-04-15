"""
Notification Service — thin wrapper used by route handlers.
Delegates to SNS service; safe to import (no side effects at module level).
"""
import logging
from backend.services.sns_service import publish_message

logger = logging.getLogger(__name__)


def send_email_notification(subject: str, message: str) -> None:
    """
    Send an email notification via AWS SNS.
    Called as a FastAPI BackgroundTask — never raises.
    """
    try:
        publish_message(subject=subject, message=message)
    except Exception as exc:
        logger.error(f"[Notification] send_email_notification failed: {exc}")

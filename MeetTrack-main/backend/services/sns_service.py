"""
SNS Service — AWS Simple Notification Service helpers.
All functions are safe to import (no code runs at module level).
"""
import boto3
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _get_sns_client():
    return boto3.client(
        "sns",
        region_name=os.getenv("AWS_REGION", "ap-south-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def subscribe_email(email: str) -> dict:
    """Subscribe an email address to the SNS topic."""
    try:
        sns = _get_sns_client()
        response = sns.subscribe(
            TopicArn=os.getenv("SNS_TOPIC_ARN"),
            Protocol="email",
            Endpoint=email,
        )
        logger.info(f"[SNS] Subscription initiated for {email} — confirm via email")
        return response
    except Exception as exc:
        logger.error(f"[SNS] subscribe_email failed: {exc}")
        return {}


def publish_message(subject: str, message: str) -> dict:
    """Publish a message to the SNS topic."""
    topic_arn = os.getenv("SNS_TOPIC_ARN")
    if not topic_arn:
        logger.warning("[SNS] SNS_TOPIC_ARN not set — skipping publish")
        return {}
    try:
        sns = _get_sns_client()
        response = sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=subject,
        )
        logger.info(f"[SNS] Published: {subject}")
        return response
    except Exception as exc:
        logger.error(f"[SNS] publish_message failed: {exc}")
        return {}


def create_notification_topic(name: str = "MeetingNotificationTopic") -> str:
    """Create an SNS topic and return its ARN."""
    try:
        sns = _get_sns_client()
        response = sns.create_topic(Name=name)
        arn = response["TopicArn"]
        logger.info(f"[SNS] Topic created: {arn}")
        return arn
    except Exception as exc:
        logger.error(f"[SNS] create_notification_topic failed: {exc}")
        return ""

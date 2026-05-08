"""
Integration Models
==================
Three tables:

1. OAuthToken       — encrypted OAuth tokens per user per provider
2. IntegrationAuditLog — every integration action logged
3. ExternalMeeting  — meetings fetched from external platforms (dedup key)
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, JSON, Index,
    Enum as SAEnum,
)
from sqlalchemy.sql import func
from backend.app.database import Base


class IntegrationProvider(str, enum.Enum):
    GOOGLE_CALENDAR  = "google_calendar"
    GOOGLE_MEET      = "google_meet"
    ZOOM             = "zoom"
    MICROSOFT_TEAMS  = "microsoft_teams"
    GOOGLE_TASKS     = "google_tasks"
    TRELLO           = "trello"
    NOTION           = "notion"
    JIRA             = "jira"


class AuditAction(str, enum.Enum):
    OAUTH_CONNECT    = "oauth_connect"
    OAUTH_DISCONNECT = "oauth_disconnect"
    TOKEN_REFRESH    = "token_refresh"
    SYNC_MEETINGS    = "sync_meetings"
    SYNC_TASKS       = "sync_tasks"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_VERIFIED = "webhook_verified"
    WEBHOOK_REJECTED = "webhook_rejected"
    REMINDER_SENT    = "reminder_sent"
    ERROR            = "error"


# ── OAuthToken ────────────────────────────────────────────────────────────────

class OAuthToken(Base):
    """
    Stores OAuth tokens per user per provider.
    access_token and refresh_token are AES-256 encrypted at rest.
    """
    __tablename__ = "oauth_tokens"
    __table_args__ = (
        Index("ix_oauth_user_provider", "user_id", "provider", unique=True),
        {"extend_existing": True},
    )

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider        = Column(SAEnum(IntegrationProvider), nullable=False)

    # Encrypted token fields (AES-256 via cryptography.fernet)
    access_token    = Column(Text, nullable=False)    # encrypted
    refresh_token   = Column(Text, nullable=True)     # encrypted
    token_type      = Column(String(50), default="Bearer")
    scope           = Column(Text, nullable=True)     # space-separated scopes

    # Expiry
    expires_at      = Column(DateTime(timezone=True), nullable=True)
    is_expired      = Column(Boolean, default=False)

    # Provider-specific IDs
    provider_user_id    = Column(String(255), nullable=True)  # e.g. Google sub
    provider_email      = Column(String(255), nullable=True)
    provider_account_name = Column(String(255), nullable=True)

    # Webhook registration
    webhook_id          = Column(String(255), nullable=True)
    webhook_secret      = Column(Text, nullable=True)         # encrypted
    webhook_expires_at  = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active       = Column(Boolean, default=True)
    last_synced_at  = Column(DateTime(timezone=True), nullable=True)
    sync_error      = Column(Text, nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ── IntegrationAuditLog ───────────────────────────────────────────────────────

class IntegrationAuditLog(Base):
    """Full audit trail of every integration action."""
    __tablename__ = "integration_audit_logs"
    __table_args__ = (
        Index("ix_audit_user_provider", "user_id", "provider"),
        Index("ix_audit_created_at",    "created_at"),
        {"extend_existing": True},
    )

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    provider    = Column(String(50), nullable=False)
    action      = Column(SAEnum(AuditAction), nullable=False)

    # Context
    resource_id   = Column(String(255), nullable=True)  # meeting_id, task_id, etc.
    resource_type = Column(String(50),  nullable=True)  # "meeting", "task", "webhook"
    details       = Column(JSON, nullable=True)          # extra context
    error_message = Column(Text, nullable=True)
    ip_address    = Column(String(45), nullable=True)

    success     = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ── ExternalMeeting ───────────────────────────────────────────────────────────

class ExternalMeeting(Base):
    """
    Tracks meetings fetched from external platforms.
    external_id is the platform's own meeting ID — used for deduplication.
    """
    __tablename__ = "external_meetings"
    __table_args__ = (
        Index("ix_ext_meeting_user_provider", "user_id", "provider"),
        Index("ix_ext_meeting_external_id",   "external_id", "provider", unique=True),
        {"extend_existing": True},
    )

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider        = Column(String(50), nullable=False)

    # External platform data
    external_id     = Column(String(255), nullable=False)   # platform meeting ID
    title           = Column(String(500), nullable=True)
    description     = Column(Text, nullable=True)
    start_time      = Column(DateTime(timezone=True), nullable=True)
    end_time        = Column(DateTime(timezone=True), nullable=True)
    duration_mins   = Column(Integer, nullable=True)
    meeting_url     = Column(Text, nullable=True)
    recording_url   = Column(Text, nullable=True)
    participants    = Column(JSON, nullable=True)   # [{name, email}, ...]
    organizer_email = Column(String(255), nullable=True)

    # Processing status
    local_meeting_id    = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    processing_status   = Column(String(50), default="pending")  # pending/processing/done/failed
    auto_processed      = Column(Boolean, default=False)

    # Raw data from platform
    raw_data        = Column(JSON, nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

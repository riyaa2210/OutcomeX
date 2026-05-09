"""
Security Audit Log
==================
Immutable append-only log of all security-relevant events.

Events logged:
  - AUTH: login, logout, failed login, token refresh, password change
  - DATA: profile updates, meeting create/delete
  - TASK: action item status changes
  - WEBHOOK: received, verified, rejected
  - SECURITY: rate limit hit, suspicious activity, RBAC denial
  - ADMIN: user role change, user deletion

Stored in PostgreSQL (security_audit_logs table).
Never deleted — only archived after 90 days.
"""

import enum
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Session

from backend.app.database import Base, SessionLocal

logger = logging.getLogger(__name__)


class AuditEventType(str, enum.Enum):
    # Auth events
    LOGIN_SUCCESS    = "auth.login_success"
    LOGIN_FAILED     = "auth.login_failed"
    LOGOUT           = "auth.logout"
    TOKEN_REFRESH    = "auth.token_refresh"
    TOKEN_REVOKED    = "auth.token_revoked"
    PASSWORD_CHANGED = "auth.password_changed"
    REGISTER         = "auth.register"

    # Data events
    PROFILE_UPDATED  = "data.profile_updated"
    MEETING_CREATED  = "data.meeting_created"
    MEETING_DELETED  = "data.meeting_deleted"
    MEETING_ACCESSED = "data.meeting_accessed"

    # Task events
    TASK_CREATED     = "task.created"
    TASK_UPDATED     = "task.updated"
    TASK_DELETED     = "task.deleted"
    TASK_STATUS_CHANGED = "task.status_changed"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_VERIFIED = "webhook.verified"
    WEBHOOK_REJECTED = "webhook.rejected"
    WEBHOOK_REPLAY   = "webhook.replay_detected"

    # Security events
    RATE_LIMIT_HIT   = "security.rate_limit"
    RBAC_DENIED      = "security.rbac_denied"
    SUSPICIOUS_IP    = "security.suspicious_ip"
    ANOMALY_DETECTED = "security.anomaly"
    CSRF_VIOLATION   = "security.csrf"
    FILE_REJECTED    = "security.file_rejected"

    # Admin events
    ROLE_CHANGED     = "admin.role_changed"
    USER_DELETED     = "admin.user_deleted"
    USER_SUSPENDED   = "admin.user_suspended"


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"
    __table_args__ = (
        Index("ix_audit_user_id",    "user_id"),
        Index("ix_audit_event_type", "event_type"),
        Index("ix_audit_created_at", "created_at"),
        Index("ix_audit_ip",         "ip_address"),
        {"extend_existing": True},
    )

    id           = Column(Integer, primary_key=True, index=True)
    event_type   = Column(String(60), nullable=False)
    user_id      = Column(Integer, nullable=True)
    user_email   = Column(String(255), nullable=True)
    user_role    = Column(String(50), nullable=True)

    # Request context
    ip_address   = Column(String(45), nullable=True)
    user_agent   = Column(String(500), nullable=True)
    endpoint     = Column(String(255), nullable=True)
    method       = Column(String(10), nullable=True)

    # Event details
    resource_type = Column(String(50), nullable=True)
    resource_id   = Column(String(100), nullable=True)
    details       = Column(JSON, nullable=True)
    old_value     = Column(Text, nullable=True)   # for data change events
    new_value     = Column(Text, nullable=True)

    # Outcome
    success      = Column(Boolean, default=True)
    risk_score   = Column(Integer, default=0)     # 0-100

    created_at   = Column(DateTime(timezone=True), server_default=func.now())


# ── Write helpers ─────────────────────────────────────────────────────────────

def log_event(
    event_type: AuditEventType,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    user_role: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    success: bool = True,
    risk_score: int = 0,
    db: Optional[Session] = None,
) -> None:
    """
    Write a security audit log entry.
    Non-blocking — errors are swallowed to never affect the main request.
    """
    _own_db = db is None
    try:
        if _own_db:
            db = SessionLocal()

        entry = SecurityAuditLog(
            event_type    = event_type.value,
            user_id       = user_id,
            user_email    = user_email,
            user_role     = user_role,
            ip_address    = ip_address,
            user_agent    = (user_agent or "")[:500],
            endpoint      = (endpoint or "")[:255],
            method        = method,
            resource_type = resource_type,
            resource_id   = str(resource_id) if resource_id else None,
            details       = details,
            old_value     = old_value,
            new_value     = new_value,
            success       = success,
            risk_score    = risk_score,
        )
        db.add(entry)
        db.commit()

    except Exception as exc:
        logger.warning(f"[AuditLog] Failed to write event {event_type.value}: {exc}")
    finally:
        if _own_db and db:
            db.close()


def log_from_request(
    request,
    event_type: AuditEventType,
    user=None,
    **kwargs,
) -> None:
    """Convenience wrapper that extracts request context automatically."""
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip", "")
        or (request.client.host if request.client else "unknown")
    )
    log_event(
        event_type = event_type,
        user_id    = getattr(user, "id", None),
        user_email = getattr(user, "email", None),
        user_role  = getattr(user, "role", None),
        ip_address = ip,
        user_agent = request.headers.get("user-agent", ""),
        endpoint   = str(request.url.path),
        method     = request.method,
        **kwargs,
    )

"""
WebhookLog model — tracks every n8n trigger attempt.

Provides:
  - Idempotency: one trigger per (meeting_id, event_type)
  - Audit trail: status, attempts, last error, n8n response
  - Retry visibility: last_attempted_at, attempt_count
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from backend.app.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    __table_args__ = {"extend_existing": True}

    id              = Column(Integer, primary_key=True, index=True)

    # What triggered this
    meeting_id      = Column(Integer, nullable=False, index=True)
    event_type      = Column(String(64), nullable=False, default="meeting_processed")
    # e.g. "meeting_processed" | "summary_generated" | "task_extracted"

    # Delivery state
    status          = Column(String(32), default="pending")
    # pending | delivered | failed | skipped

    attempt_count   = Column(Integer, default=0)
    max_attempts    = Column(Integer, default=3)

    # Response from n8n
    n8n_status_code = Column(Integer, nullable=True)
    n8n_response    = Column(Text, nullable=True)   # first 2000 chars of body
    last_error      = Column(Text, nullable=True)

    # Idempotency key: SHA-256 of (meeting_id + event_type + payload hash)
    idempotency_key = Column(String(64), unique=True, nullable=False, index=True)

    # Timestamps
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    last_attempted_at   = Column(DateTime(timezone=True), nullable=True)
    delivered_at        = Column(DateTime(timezone=True), nullable=True)

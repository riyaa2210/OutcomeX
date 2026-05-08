"""
TaskLog — PostgreSQL table for Celery task execution history.

Stores every task dispatch, state transition, result, and error.
Used by the task monitoring dashboard and idempotency checks.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Enum as SAEnum, Index, JSON,
)
from sqlalchemy.sql import func

from backend.app.database import Base


class TaskState(str, enum.Enum):
    QUEUED     = "queued"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"
    RETRYING   = "retrying"
    REVOKED    = "revoked"


class TaskLog(Base):
    __tablename__ = "task_logs"
    __table_args__ = (
        Index("ix_task_logs_celery_id",    "celery_task_id"),
        Index("ix_task_logs_idempotency",  "idempotency_key", unique=True),
        Index("ix_task_logs_meeting_type", "meeting_id", "task_type"),
        Index("ix_task_logs_state",        "state"),
        Index("ix_task_logs_created_at",   "created_at"),
        {"extend_existing": True},
    )

    id              = Column(Integer, primary_key=True, index=True)

    # Celery identity
    celery_task_id  = Column(String(255), nullable=True, index=True)
    task_type       = Column(String(100), nullable=False)   # e.g. "transcription", "ai_extraction"
    task_name       = Column(String(255), nullable=True)    # full dotted task name

    # Business context
    meeting_id      = Column(Integer, nullable=True)
    user_id         = Column(Integer, nullable=True)
    idempotency_key = Column(String(64), nullable=True, unique=True)

    # State machine
    state           = Column(SAEnum(TaskState), default=TaskState.QUEUED, nullable=False)

    # Timing
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    started_at      = Column(DateTime(timezone=True), nullable=True)
    completed_at    = Column(DateTime(timezone=True), nullable=True)
    duration_secs   = Column(Float, nullable=True)

    # Retry tracking
    attempt_number  = Column(Integer, default=1)
    max_attempts    = Column(Integer, default=3)

    # Payload / result
    input_summary   = Column(Text, nullable=True)    # short description of input
    result_summary  = Column(Text, nullable=True)    # short description of result
    error_message   = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Extra metadata (JSON blob)
    meta            = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<TaskLog id={self.id} type={self.task_type} state={self.state}>"

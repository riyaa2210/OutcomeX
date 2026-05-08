"""
Task Logger — DB helper for recording Celery task lifecycle events.

All Celery tasks call these helpers to write state transitions into
the task_logs table, giving the monitoring dashboard full visibility.
"""

import hashlib
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.models.task_log import TaskLog, TaskState

logger = logging.getLogger(__name__)


# ── Session context manager ───────────────────────────────────────────────────

def get_db() -> Session:
    """Create a fresh DB session for use inside a Celery task."""
    return SessionLocal()


# ── Idempotency key ───────────────────────────────────────────────────────────

def make_idempotency_key(task_type: str, *args) -> str:
    """
    SHA-256 of task_type + all positional args.
    Guarantees one execution per unique (task_type, args) combination.
    """
    raw = ":".join([task_type] + [str(a) for a in args])
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Check duplicate ───────────────────────────────────────────────────────────

def is_duplicate(db: Session, idempotency_key: str) -> Optional[TaskLog]:
    """
    Return existing TaskLog if this task was already completed successfully.
    Returns None if safe to proceed.
    """
    existing = db.query(TaskLog).filter(
        TaskLog.idempotency_key == idempotency_key
    ).first()

    if existing and existing.state == TaskState.COMPLETED:
        return existing
    return None


# ── Create log entry ──────────────────────────────────────────────────────────

def create_log(
    db: Session,
    task_type: str,
    task_name: str,
    celery_task_id: str,
    idempotency_key: str,
    meeting_id: Optional[int] = None,
    user_id: Optional[int] = None,
    input_summary: Optional[str] = None,
    max_attempts: int = 3,
    meta: Optional[dict] = None,
) -> TaskLog:
    """Create a new TaskLog row in QUEUED state."""
    # Upsert: if a failed/retrying log exists for this key, reuse it
    existing = db.query(TaskLog).filter(
        TaskLog.idempotency_key == idempotency_key
    ).first()

    if existing:
        existing.celery_task_id = celery_task_id
        existing.state          = TaskState.QUEUED
        existing.error_message  = None
        existing.attempt_number = (existing.attempt_number or 0) + 1
        db.commit()
        db.refresh(existing)
        return existing

    log = TaskLog(
        celery_task_id  = celery_task_id,
        task_type       = task_type,
        task_name       = task_name,
        meeting_id      = meeting_id,
        user_id         = user_id,
        idempotency_key = idempotency_key,
        state           = TaskState.QUEUED,
        input_summary   = input_summary,
        max_attempts    = max_attempts,
        meta            = meta or {},
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ── State transitions ─────────────────────────────────────────────────────────

def mark_processing(db: Session, log: TaskLog) -> None:
    log.state      = TaskState.PROCESSING
    log.started_at = datetime.now(timezone.utc)
    db.commit()


def mark_completed(db: Session, log: TaskLog, result_summary: str = "") -> None:
    now = datetime.now(timezone.utc)
    log.state          = TaskState.COMPLETED
    log.completed_at   = now
    log.result_summary = result_summary[:500] if result_summary else ""
    if log.started_at:
        log.duration_secs = (now - log.started_at).total_seconds()
    db.commit()


def mark_failed(
    db: Session,
    log: TaskLog,
    error: Exception,
    retrying: bool = False,
) -> None:
    log.state           = TaskState.RETRYING if retrying else TaskState.FAILED
    log.error_message   = str(error)[:1000]
    log.error_traceback = traceback.format_exc()[:3000]
    db.commit()


def mark_dead_letter(db: Session, log: TaskLog, reason: str) -> None:
    """Move to FAILED after all retries exhausted."""
    log.state         = TaskState.FAILED
    log.error_message = f"[DEAD LETTER] {reason}"[:1000]
    db.commit()

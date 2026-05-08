"""
Task Status Routes — Async API + Monitoring Dashboard
======================================================

Async processing pattern:
  POST /process-async   → returns {task_id, status_url}
  GET  /tasks/{task_id} → poll task state

Monitoring dashboard:
  GET /tasks/dashboard  → overview of all task states
  GET /tasks/logs       → paginated task execution log
  GET /tasks/stats      → aggregate stats by task type
  DELETE /tasks/{id}    → revoke a queued/running task
"""

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.task_log import TaskLog, TaskState
from backend.models.meeting import Meeting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["Tasks"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Async process endpoint ────────────────────────────────────────────────────

class AsyncProcessRequest(BaseModel):
    file_path: str
    file_name: str = "Unknown"


class AsyncTranscriptRequest(BaseModel):
    transcript: str
    title: str = "Untitled Meeting"


@router.post("/process-async")
async def process_meeting_async(
    request: AsyncProcessRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Async meeting processing — returns task_id immediately.
    Client polls GET /tasks/{task_id} for status.

    Flow: upload → transcription_task → ai_extraction_task → webhook + email + rag
    """
    if not request.file_path or not os.path.exists(request.file_path):
        raise HTTPException(status_code=400, detail="File not found")

    # Create meeting stub
    title = (
        request.file_name
        .replace(".mp3", "").replace(".wav", "")
        .replace(".m4a", "").replace(".ogg", "").strip()
        or "Untitled Meeting"
    )
    meeting = Meeting(
        user_id    = current_user.id,
        title      = title,
        audio_path = request.file_path,
        created_at = datetime.utcnow(),
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Dispatch transcription task
    from backend.worker.tasks.transcription_tasks import transcribe_audio_task
    task = transcribe_audio_task.apply_async(
        args=[meeting.id, request.file_path, current_user.id],
        queue="transcription",
    )

    return {
        "task_id":    task.id,
        "meeting_id": meeting.id,
        "status":     "queued",
        "status_url": f"/tasks/{task.id}",
        "message":    "Processing started. Poll status_url for updates.",
    }


@router.post("/process-transcript-async")
async def process_transcript_async(
    request: AsyncTranscriptRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Async transcript processing — skips transcription, goes straight to AI.
    Returns task_id immediately.
    """
    if not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty")

    meeting = Meeting(
        user_id    = current_user.id,
        title      = request.title or "Untitled Meeting",
        transcript = request.transcript,
        created_at = datetime.utcnow(),
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    from backend.worker.tasks.ai_tasks import ai_extraction_task
    task = ai_extraction_task.apply_async(
        args=[meeting.id, current_user.id],
        queue="ai_extraction",
    )

    return {
        "task_id":    task.id,
        "meeting_id": meeting.id,
        "status":     "queued",
        "status_url": f"/tasks/{task.id}",
        "message":    "AI extraction started. Poll status_url for updates.",
    }


@router.post("/upload-and-process")
async def upload_and_process_async(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload audio + immediately queue async processing.
    Single endpoint for the frontend — returns task_id.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, file.filename))
    with open(file_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    title = (
        file.filename
        .replace(".mp3", "").replace(".wav", "")
        .replace(".m4a", "").replace(".ogg", "").strip()
        or "Untitled Meeting"
    )
    meeting = Meeting(
        user_id    = current_user.id,
        title      = title,
        audio_path = file_path,
        created_at = datetime.utcnow(),
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    from backend.worker.tasks.transcription_tasks import transcribe_audio_task
    task = transcribe_audio_task.apply_async(
        args=[meeting.id, file_path, current_user.id],
        queue="transcription",
    )

    return {
        "task_id":    task.id,
        "meeting_id": meeting.id,
        "status":     "queued",
        "status_url": f"/tasks/{task.id}",
        "file_name":  file.filename,
    }


# ── Poll task status ──────────────────────────────────────────────────────────

@router.get("/{task_id}")
def get_task_status(
    task_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Poll the status of a Celery task.
    Returns DB log + live Celery state.
    """
    # Check DB log first (most reliable)
    log = db.query(TaskLog).filter(TaskLog.celery_task_id == task_id).first()

    # Also check Celery result backend
    celery_state = None
    celery_result = None
    try:
        from backend.worker.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        celery_state = result.state
        if result.ready() and result.successful():
            celery_result = result.result
    except Exception:
        pass

    if not log:
        # Task not in DB yet — use Celery state
        return {
            "task_id":      task_id,
            "state":        (celery_state or "PENDING").lower(),
            "celery_state": celery_state,
            "result":       celery_result,
        }

    return {
        "task_id":        task_id,
        "state":          log.state.value,
        "task_type":      log.task_type,
        "meeting_id":     log.meeting_id,
        "attempt":        log.attempt_number,
        "max_attempts":   log.max_attempts,
        "created_at":     log.created_at.isoformat() if log.created_at else None,
        "started_at":     log.started_at.isoformat() if log.started_at else None,
        "completed_at":   log.completed_at.isoformat() if log.completed_at else None,
        "duration_secs":  log.duration_secs,
        "result_summary": log.result_summary,
        "error_message":  log.error_message,
        "celery_state":   celery_state,
        "result":         celery_result,
    }


# ── Revoke task ───────────────────────────────────────────────────────────────

@router.delete("/{task_id}/revoke")
def revoke_task(
    task_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a queued or running task."""
    try:
        from backend.worker.celery_app import celery_app
        celery_app.control.revoke(task_id, terminate=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Revoke failed: {exc}")

    log = db.query(TaskLog).filter(TaskLog.celery_task_id == task_id).first()
    if log:
        log.state = TaskState.REVOKED
        db.commit()

    return {"task_id": task_id, "revoked": True}


# ── Monitoring dashboard ──────────────────────────────────────────────────────

@router.get("/dashboard/overview")
def get_dashboard_overview(
    hours: int = Query(24, ge=1, le=168),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Task monitoring dashboard — aggregate stats for the last N hours.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # State counts
    state_counts = db.execute(text("""
        SELECT state, COUNT(*) AS cnt
        FROM task_logs
        WHERE created_at >= :since
        GROUP BY state
    """), {"since": since}).fetchall()

    states = {row.state: int(row.cnt) for row in state_counts}

    # By task type
    type_counts = db.execute(text("""
        SELECT task_type,
               COUNT(*) AS total,
               COUNT(CASE WHEN state = 'completed' THEN 1 END) AS completed,
               COUNT(CASE WHEN state = 'failed'    THEN 1 END) AS failed,
               AVG(CASE WHEN duration_secs IS NOT NULL THEN duration_secs END) AS avg_duration
        FROM task_logs
        WHERE created_at >= :since
        GROUP BY task_type
        ORDER BY total DESC
    """), {"since": since}).fetchall()

    by_type = [
        {
            "task_type":    row.task_type,
            "total":        int(row.total),
            "completed":    int(row.completed),
            "failed":       int(row.failed),
            "success_rate": round(int(row.completed) / int(row.total) * 100, 1) if row.total else 0,
            "avg_duration": round(float(row.avg_duration), 2) if row.avg_duration else None,
        }
        for row in type_counts
    ]

    # Recent failures
    recent_failures = db.query(TaskLog).filter(
        TaskLog.state == TaskState.FAILED,
        TaskLog.created_at >= since,
    ).order_by(TaskLog.created_at.desc()).limit(10).all()

    # Throughput per hour
    throughput = db.execute(text("""
        SELECT DATE_TRUNC('hour', created_at) AS hour, COUNT(*) AS cnt
        FROM task_logs
        WHERE created_at >= :since
        GROUP BY hour
        ORDER BY hour ASC
    """), {"since": since}).fetchall()

    # Worker queue depths (requires Celery inspect — graceful fallback)
    queue_depths = {}
    try:
        from backend.worker.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        active  = inspect.active() or {}
        reserved = inspect.reserved() or {}
        for worker, tasks in active.items():
            queue_depths[worker] = {"active": len(tasks), "reserved": len(reserved.get(worker, []))}
    except Exception:
        pass

    return {
        "period_hours":    hours,
        "state_summary":   states,
        "total_tasks":     sum(states.values()),
        "by_task_type":    by_type,
        "recent_failures": [
            {
                "id":            f.id,
                "task_type":     f.task_type,
                "meeting_id":    f.meeting_id,
                "error_message": f.error_message,
                "created_at":    f.created_at.isoformat() if f.created_at else None,
            }
            for f in recent_failures
        ],
        "throughput_per_hour": [
            {"hour": row.hour.isoformat(), "count": int(row.cnt)}
            for row in throughput
        ],
        "worker_queue_depths": queue_depths,
    }


@router.get("/dashboard/logs")
def get_task_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    meeting_id: Optional[int] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated task execution log with filters."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    q = db.query(TaskLog).filter(TaskLog.created_at >= since)

    if task_type:
        q = q.filter(TaskLog.task_type == task_type)
    if state:
        q = q.filter(TaskLog.state == state)
    if meeting_id:
        q = q.filter(TaskLog.meeting_id == meeting_id)

    total = q.count()
    logs  = q.order_by(TaskLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "logs": [
            {
                "id":             l.id,
                "celery_task_id": l.celery_task_id,
                "task_type":      l.task_type,
                "state":          l.state.value,
                "meeting_id":     l.meeting_id,
                "attempt":        l.attempt_number,
                "duration_secs":  l.duration_secs,
                "result_summary": l.result_summary,
                "error_message":  l.error_message,
                "created_at":     l.created_at.isoformat() if l.created_at else None,
                "completed_at":   l.completed_at.isoformat() if l.completed_at else None,
            }
            for l in logs
        ],
    }


@router.get("/dashboard/stats")
def get_task_stats(
    days: int = Query(7, ge=1, le=90),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate task stats for the last N days — for charts."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.execute(text("""
        SELECT
            DATE_TRUNC('day', created_at) AS day,
            task_type,
            COUNT(*) AS total,
            COUNT(CASE WHEN state = 'completed' THEN 1 END) AS completed,
            COUNT(CASE WHEN state = 'failed'    THEN 1 END) AS failed,
            AVG(duration_secs) AS avg_duration
        FROM task_logs
        WHERE created_at >= :since
        GROUP BY day, task_type
        ORDER BY day ASC, task_type
    """), {"since": since}).fetchall()

    return {
        "data": [
            {
                "day":          row.day.strftime("%Y-%m-%d") if row.day else "",
                "task_type":    row.task_type,
                "total":        int(row.total),
                "completed":    int(row.completed),
                "failed":       int(row.failed),
                "avg_duration": round(float(row.avg_duration), 2) if row.avg_duration else None,
            }
            for row in rows
        ]
    }

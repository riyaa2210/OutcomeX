"""
Webhook Routes — admin/debug endpoints for the n8n integration.

GET  /webhook/status          — is n8n reachable?
GET  /webhook/logs            — recent delivery log
GET  /webhook/logs/{meeting}  — logs for a specific meeting
POST /webhook/test            — fire a test payload to n8n
POST /webhook/retry/{meeting} — manually retry a failed delivery
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.webhook_log import WebhookLog
from backend.services.n8n_service import ping_n8n, trigger_n8n_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["Webhook / n8n"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── health check ──────────────────────────────────────────────────────────────

@router.get("/status")
def webhook_status():
    """Check whether n8n is reachable from the backend."""
    result = ping_n8n()
    return {
        "n8n_reachable": result["reachable"],
        "n8n_url":       result["url"],
        "error":         result["error"],
        "tip": (
            "Start n8n with: npx n8n"
            if not result["reachable"] else
            "n8n is up and accepting webhooks"
        ),
    }


# ── delivery logs ─────────────────────────────────────────────────────────────

@router.get("/logs")
def get_webhook_logs(
    limit: int = 50,
    status: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return recent webhook delivery logs (newest first)."""
    query = db.query(WebhookLog).order_by(WebhookLog.created_at.desc())
    if status:
        query = query.filter(WebhookLog.status == status)
    logs = query.limit(limit).all()

    return [
        {
            "id":               log.id,
            "meeting_id":       log.meeting_id,
            "event_type":       log.event_type,
            "status":           log.status,
            "attempt_count":    log.attempt_count,
            "n8n_status_code":  log.n8n_status_code,
            "last_error":       log.last_error,
            "created_at":       log.created_at,
            "delivered_at":     log.delivered_at,
            "last_attempted_at":log.last_attempted_at,
        }
        for log in logs
    ]


@router.get("/logs/{meeting_id}")
def get_logs_for_meeting(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all webhook logs for a specific meeting."""
    logs = (
        db.query(WebhookLog)
        .filter(WebhookLog.meeting_id == meeting_id)
        .order_by(WebhookLog.created_at.desc())
        .all()
    )
    if not logs:
        raise HTTPException(status_code=404, detail="No webhook logs for this meeting")

    return [
        {
            "id":               log.id,
            "event_type":       log.event_type,
            "status":           log.status,
            "attempt_count":    log.attempt_count,
            "n8n_status_code":  log.n8n_status_code,
            "n8n_response":     log.n8n_response,
            "last_error":       log.last_error,
            "created_at":       log.created_at,
            "delivered_at":     log.delivered_at,
        }
        for log in logs
    ]


# ── test fire ─────────────────────────────────────────────────────────────────

@router.post("/test")
def test_webhook(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fire a synthetic test payload to n8n.
    Use this to verify your n8n workflow is connected without processing a real meeting.
    """
    test_structured = {
        "summary":   "This is a test payload from MeetTrack backend.",
        "decisions": ["Use n8n for automation", "Deploy by end of sprint"],
        "action_items": [
            {"task": "Verify n8n webhook", "assignee": "Dev Team",
             "deadline": None, "confidence_score": 1.0},
        ],
    }

    log = trigger_n8n_workflow(
        db=db,
        meeting_id=0,           # 0 = test, not a real meeting
        transcript="Test transcript — no real audio processed.",
        structured=test_structured,
        event_type="test_ping",
    )

    return {
        "test_sent":        True,
        "n8n_status_code":  log.n8n_status_code if log else None,
        "delivery_status":  log.status if log else "unknown",
        "n8n_response":     log.n8n_response if log else None,
        "tip": (
            "If status is 'failed', make sure n8n is running: npx n8n"
            if (log and log.status == "failed") else
            "Payload delivered — check your n8n execution log"
        ),
    }


# ── manual retry ──────────────────────────────────────────────────────────────

@router.post("/retry/{meeting_id}")
def retry_webhook(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually retry a failed webhook delivery for a meeting.
    Resets the idempotency key so a fresh attempt is made.
    """
    from backend.models.meeting import Meeting

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="Meeting has no transcript to send")

    # Delete old failed log so idempotency check doesn't block retry
    old_log = (
        db.query(WebhookLog)
        .filter(
            WebhookLog.meeting_id == meeting_id,
            WebhookLog.event_type == "meeting_processed",
        )
        .first()
    )
    if old_log and old_log.status == "delivered":
        return {"message": "Already delivered — no retry needed", "status": "delivered"}

    if old_log:
        db.delete(old_log)
        db.commit()

    # Re-trigger
    log = trigger_n8n_workflow(
        db=db,
        meeting_id=meeting_id,
        transcript=meeting.transcript,
        structured={"summary": "", "decisions": [], "action_items": []},
        event_type="meeting_processed",
    )

    return {
        "retried":         True,
        "meeting_id":      meeting_id,
        "delivery_status": log.status if log else "unknown",
        "n8n_status_code": log.n8n_status_code if log else None,
    }

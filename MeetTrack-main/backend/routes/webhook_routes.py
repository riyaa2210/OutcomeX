"""
Webhook / Automation Routes
===========================
Admin + debug endpoints for the Activepieces integration.

GET  /webhook/status          — is Activepieces reachable?
GET  /webhook/logs            — recent delivery log
GET  /webhook/logs/{id}       — logs for a specific meeting
POST /webhook/test            — fire a test payload
POST /webhook/retry/{id}      — manually retry a failed delivery
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.webhook_log import WebhookLog
from backend.services.automation_service import (
    ping_automation,
    trigger_automation,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["Webhook / Automation"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/status")
def webhook_status():
    """Check whether Activepieces webhook is reachable."""
    result = ping_automation()
    return {
        "reachable": result["reachable"],
        "url":       result["url"],
        "error":     result["error"],
        "platform":  "Activepieces",
        "tip": (
            "Set ACTIVEPIECES_WEBHOOK_URL in environment variables"
            if not result["url"] else
            "Activepieces webhook is configured"
            if result["reachable"] else
            "Cannot reach Activepieces — check the URL"
        ),
    }


# ── Delivery logs ─────────────────────────────────────────────────────────────

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
            "id":                log.id,
            "meeting_id":        log.meeting_id,
            "event_type":        log.event_type,
            "status":            log.status,
            "attempt_count":     log.attempt_count,
            "status_code":       log.n8n_status_code,
            "last_error":        log.last_error,
            "created_at":        log.created_at,
            "delivered_at":      log.delivered_at,
            "last_attempted_at": log.last_attempted_at,
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
            "id":            log.id,
            "event_type":    log.event_type,
            "status":        log.status,
            "attempt_count": log.attempt_count,
            "status_code":   log.n8n_status_code,
            "response":      log.n8n_response,
            "last_error":    log.last_error,
            "created_at":    log.created_at,
            "delivered_at":  log.delivered_at,
        }
        for log in logs
    ]


# ── Test fire ─────────────────────────────────────────────────────────────────

@router.post("/test")
def test_webhook(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fire a synthetic test payload to Activepieces."""
    test_structured = {
        "summary":   "Test payload from OutcomeX backend.",
        "decisions": ["Adopt Activepieces for automation", "Deploy by end of sprint"],
        "action_items": [
            {
                "task":             "Verify Activepieces webhook",
                "assignee":         "Dev Team",
                "deadline":         None,
                "confidence_score": 1.0,
            }
        ],
    }

    log = trigger_automation(
        db=db,
        meeting_id=0,
        transcript="Test transcript.",
        structured=test_structured,
        event_type="test_ping",
    )

    return {
        "test_sent":       True,
        "status_code":     log.n8n_status_code if log else None,
        "delivery_status": log.status if log else "skipped",
        "response":        log.n8n_response if log else None,
    }


# ── Manual retry ──────────────────────────────────────────────────────────────

@router.post("/retry/{meeting_id}")
def retry_webhook(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually retry a failed delivery for a meeting."""
    from backend.models.meeting import Meeting

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="Meeting has no transcript")

    # Delete old log to reset idempotency
    old_log = (
        db.query(WebhookLog)
        .filter(
            WebhookLog.meeting_id == meeting_id,
            WebhookLog.event_type == "meeting_processed",
        )
        .first()
    )
    if old_log and old_log.status == "delivered":
        return {"message": "Already delivered", "status": "delivered"}
    if old_log:
        db.delete(old_log)
        db.commit()

    log = trigger_automation(
        db=db,
        meeting_id=meeting_id,
        transcript=meeting.transcript,
        structured={"summary": "", "decisions": [], "action_items": []},
        event_type="meeting_processed",
    )

    return {
        "retried":         True,
        "meeting_id":      meeting_id,
        "delivery_status": log.status if log else "skipped",
        "status_code":     log.n8n_status_code if log else None,
    }

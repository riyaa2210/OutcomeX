"""
Integration Routes
==================

OAuth:
  GET  /integrations/oauth/{provider}/authorize  — get auth URL
  GET  /integrations/oauth/{provider}/callback   — handle OAuth callback
  DELETE /integrations/{provider}                — disconnect

Status:
  GET  /integrations                             — list all connected integrations
  GET  /integrations/audit                       — audit log

Calendar sync:
  POST /integrations/sync/calendar               — fetch meetings from all connected platforms
  GET  /integrations/meetings                    — list synced external meetings
  POST /integrations/meetings/{id}/process       — trigger AI processing for an external meeting

Task sync:
  POST /integrations/sync/tasks/{meeting_id}     — push action items to connected task managers
  POST /integrations/reminders/{action_item_id}  — create calendar reminder

Webhooks:
  POST /integrations/webhooks/zoom               — Zoom webhook receiver
  POST /integrations/webhooks/google             — Google Calendar push notification
  POST /integrations/webhooks/teams              — Teams change notification
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.integration import (
    OAuthToken, IntegrationAuditLog, ExternalMeeting,
    IntegrationProvider, AuditAction,
)
from backend.models.action_item import ActionItem
from backend.services.integration.oauth_service import (
    get_authorization_url, exchange_code, disconnect_provider,
    get_valid_token, _audit,
)
from backend.services.integration.calendar_service import (
    fetch_google_calendar_events, fetch_zoom_meetings,
    fetch_teams_meetings, sync_external_meetings,
)
from backend.services.integration.task_sync_service import (
    sync_to_google_tasks, sync_to_trello, sync_to_notion, sync_to_jira,
    create_calendar_reminder,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["Integrations"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://automated-meeting-outcome-tracker.onrender.com")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── OAuth authorize ───────────────────────────────────────────────────────────

@router.get("/oauth/{provider}/authorize")
def authorize(
    provider: str,
    current_user=Depends(get_current_user),
):
    """Return the OAuth authorization URL for a provider."""
    try:
        prov = IntegrationProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    try:
        result = get_authorization_url(prov, current_user.id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── OAuth callback ────────────────────────────────────────────────────────────

@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from provider.
    Exchanges code for tokens, stores encrypted, redirects to frontend.
    """
    if error:
        logger.warning(f"[OAuth] Callback error for {provider}: {error}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/profile?integration_error={provider}&reason={error}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/profile?integration_error={provider}&reason=missing_params"
        )

    try:
        prov = IntegrationProvider(provider)
    except ValueError:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/profile?integration_error={provider}&reason=unknown_provider"
        )

    try:
        token = exchange_code(db, prov, code, state)
        logger.info(f"[OAuth] Connected {provider} for user={token.user_id}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/profile?integration_success={provider}"
        )
    except Exception as exc:
        logger.error(f"[OAuth] Callback failed for {provider}: {exc}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/profile?integration_error={provider}&reason=token_exchange_failed"
        )


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/{provider}")
def disconnect(
    provider: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disconnect and revoke an integration."""
    try:
        prov = IntegrationProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    disconnect_provider(db, current_user.id, prov)
    return {"disconnected": True, "provider": provider}


# ── List integrations ─────────────────────────────────────────────────────────

@router.get("")
def list_integrations(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all connected integrations for the current user."""
    tokens = db.query(OAuthToken).filter(
        OAuthToken.user_id == current_user.id,
        OAuthToken.is_active == True,
    ).all()

    # All supported providers with connection status
    all_providers = [p.value for p in IntegrationProvider]
    connected = {t.provider.value: t for t in tokens}

    result = []
    for prov in all_providers:
        token = connected.get(prov)
        result.append({
            "provider":          prov,
            "connected":         prov in connected,
            "provider_email":    token.provider_email if token else None,
            "provider_account":  token.provider_account_name if token else None,
            "last_synced_at":    token.last_synced_at.isoformat() if token and token.last_synced_at else None,
            "is_expired":        token.is_expired if token else False,
            "sync_error":        token.sync_error if token else None,
            "scopes":            token.scope if token else None,
        })

    return {"integrations": result}


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated integration audit log."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(IntegrationAuditLog).filter(
        IntegrationAuditLog.user_id == current_user.id,
        IntegrationAuditLog.created_at >= since,
    )
    if provider:
        q = q.filter(IntegrationAuditLog.provider == provider)

    total = q.count()
    logs  = q.order_by(IntegrationAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page":  page,
        "pages": (total + page_size - 1) // page_size,
        "logs": [
            {
                "id":            l.id,
                "provider":      l.provider,
                "action":        l.action.value,
                "resource_id":   l.resource_id,
                "resource_type": l.resource_type,
                "details":       l.details,
                "success":       l.success,
                "error_message": l.error_message,
                "created_at":    l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


# ── Calendar sync ─────────────────────────────────────────────────────────────

@router.post("/sync/calendar")
def sync_calendar(
    days_back: int = Query(30, ge=1, le=90),
    days_ahead: int = Query(7, ge=0, le=30),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch meetings from all connected calendar platforms."""
    all_events = []

    # Google Calendar
    gc_token = get_valid_token(db, current_user.id, IntegrationProvider.GOOGLE_CALENDAR)
    if gc_token:
        events = fetch_google_calendar_events(db, current_user.id, days_ahead, days_back)
        all_events.extend(events)

    # Zoom
    zoom_token = get_valid_token(db, current_user.id, IntegrationProvider.ZOOM)
    if zoom_token:
        events = fetch_zoom_meetings(db, current_user.id)
        all_events.extend(events)

    # Microsoft Teams
    teams_token = get_valid_token(db, current_user.id, IntegrationProvider.MICROSOFT_TEAMS)
    if teams_token:
        events = fetch_teams_meetings(db, current_user.id, days_ahead, days_back)
        all_events.extend(events)

    if not all_events:
        return {"message": "No calendar integrations connected or no events found", "synced": 0}

    result = sync_external_meetings(db, current_user.id, all_events)
    return {
        "message": f"Synced {result['new']} new meetings",
        **result,
        "total_fetched": len(all_events),
    }


# ── External meetings list ────────────────────────────────────────────────────

@router.get("/meetings")
def list_external_meetings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List synced external meetings."""
    q = db.query(ExternalMeeting).filter(ExternalMeeting.user_id == current_user.id)
    if provider:
        q = q.filter(ExternalMeeting.provider == provider)
    if status:
        q = q.filter(ExternalMeeting.processing_status == status)

    total = q.count()
    items = q.order_by(ExternalMeeting.start_time.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page":  page,
        "pages": (total + page_size - 1) // page_size,
        "meetings": [
            {
                "id":                em.id,
                "provider":          em.provider,
                "external_id":       em.external_id,
                "title":             em.title,
                "start_time":        em.start_time.isoformat() if em.start_time else None,
                "end_time":          em.end_time.isoformat() if em.end_time else None,
                "duration_mins":     em.duration_mins,
                "meeting_url":       em.meeting_url,
                "recording_url":     em.recording_url,
                "participants":      em.participants or [],
                "organizer_email":   em.organizer_email,
                "processing_status": em.processing_status,
                "local_meeting_id":  em.local_meeting_id,
                "auto_processed":    em.auto_processed,
            }
            for em in items
        ],
    }


# ── Process external meeting ──────────────────────────────────────────────────

@router.post("/meetings/{external_meeting_id}/process")
def process_external_meeting(
    external_meeting_id: int,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger AI processing for an external meeting (transcript from recording)."""
    em = db.query(ExternalMeeting).filter(
        ExternalMeeting.id == external_meeting_id,
        ExternalMeeting.user_id == current_user.id,
    ).first()
    if not em:
        raise HTTPException(status_code=404, detail="External meeting not found")

    if em.processing_status == "processing":
        return {"message": "Already processing", "status": "processing"}

    em.processing_status = "processing"
    db.commit()

    # Queue Celery task if recording URL available
    if em.recording_url:
        try:
            from backend.worker.tasks.transcription_tasks import transcribe_audio_task
            # For external recordings, we'd need to download first
            # For now, mark as needing manual transcript
            em.processing_status = "pending_transcript"
            db.commit()
            return {
                "message": "Recording URL found. Download and upload the recording to process.",
                "recording_url": em.recording_url,
                "status": "pending_transcript",
            }
        except ImportError:
            pass

    return {
        "message": "No recording URL. Paste the transcript manually to process.",
        "status": em.processing_status,
        "external_id": em.external_id,
    }


# ── Task sync ─────────────────────────────────────────────────────────────────

class TaskSyncRequest(BaseModel):
    providers: list[str]  # ["google_tasks", "trello", "notion", "jira"]
    project_key: Optional[str] = None   # Jira project key
    board_id: Optional[str] = None      # Trello board ID
    database_id: Optional[str] = None   # Notion database ID


@router.post("/sync/tasks/{meeting_id}")
def sync_tasks(
    meeting_id: int,
    req: TaskSyncRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Push action items from a meeting to connected task managers."""
    action_items = db.query(ActionItem).filter(
        ActionItem.meeting_id == meeting_id,
        ActionItem.status.notin_(["Completed", "Done", "done", "completed"]),
    ).all()

    if not action_items:
        return {"message": "No pending action items found", "results": {}}

    results = {}

    for provider_str in req.providers:
        if provider_str == "google_tasks":
            results["google_tasks"] = sync_to_google_tasks(db, current_user.id, action_items)
        elif provider_str == "trello":
            results["trello"] = sync_to_trello(
                db, current_user.id, action_items,
                board_id=req.board_id,
            )
        elif provider_str == "notion":
            results["notion"] = sync_to_notion(
                db, current_user.id, action_items,
                database_id=req.database_id,
            )
        elif provider_str == "jira":
            results["jira"] = sync_to_jira(
                db, current_user.id, action_items,
                project_key=req.project_key,
            )

    return {
        "meeting_id":    meeting_id,
        "items_synced":  len(action_items),
        "results":       results,
    }


# ── Calendar reminders ────────────────────────────────────────────────────────

@router.post("/reminders/{action_item_id}")
def create_reminder(
    action_item_id: int,
    reminder_minutes: int = Query(60, ge=5, le=10080),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Google Calendar reminder for a pending action item."""
    item = db.query(ActionItem).filter(ActionItem.id == action_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")

    result = create_calendar_reminder(db, current_user.id, item, reminder_minutes)
    return result


# ── Webhook receivers ─────────────────────────────────────────────────────────

@router.post("/webhooks/zoom")
async def zoom_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Zoom webhook events.
    Verifies HMAC-SHA256 signature before processing.
    """
    body = await request.body()
    signature = request.headers.get("x-zm-signature", "")
    timestamp  = request.headers.get("x-zm-request-timestamp", "")
    secret     = os.getenv("ZOOM_WEBHOOK_SECRET", "")

    # Verify signature
    if secret:
        msg = f"v0:{timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            _audit(db, None, "zoom", AuditAction.WEBHOOK_REJECTED,
                   details={"reason": "invalid_signature"})
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
        event   = payload.get("event", "")

        _audit(db, None, "zoom", AuditAction.WEBHOOK_RECEIVED,
               details={"event": event})

        # Handle recording completed
        if event == "recording.completed":
            meeting_data = payload.get("payload", {}).get("object", {})
            _handle_zoom_recording_completed(db, meeting_data)

        # Zoom URL validation challenge
        if event == "endpoint.url_validation":
            plain_token = payload.get("payload", {}).get("plainToken", "")
            enc_token   = hmac.new(secret.encode(), plain_token.encode(), hashlib.sha256).hexdigest()
            return {"plainToken": plain_token, "encryptedToken": enc_token}

    except Exception as exc:
        logger.error(f"[Webhook] Zoom processing error: {exc}")

    return {"received": True}


def _handle_zoom_recording_completed(db: Session, meeting_data: dict) -> None:
    """Auto-process a Zoom meeting when recording is complete."""
    meeting_id = str(meeting_data.get("id", ""))
    if not meeting_id:
        return

    # Find the external meeting
    em = db.query(ExternalMeeting).filter(
        ExternalMeeting.external_id == meeting_id,
        ExternalMeeting.provider    == "zoom",
    ).first()

    if em:
        rec_files = meeting_data.get("recording_files", [])
        rec_url   = next(
            (f.get("download_url") for f in rec_files if f.get("file_type") == "MP4"),
            None,
        )
        if rec_url:
            em.recording_url      = rec_url
            em.processing_status  = "pending"
            em.auto_processed     = False
            db.commit()
            logger.info(f"[Webhook] Zoom recording ready for meeting {meeting_id}")


@router.post("/webhooks/google")
async def google_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Google Calendar push notifications."""
    channel_id = request.headers.get("x-goog-channel-id", "")
    resource_state = request.headers.get("x-goog-resource-state", "")

    _audit(db, None, "google_calendar", AuditAction.WEBHOOK_RECEIVED,
           details={"channel_id": channel_id, "state": resource_state})

    # sync is triggered — we'd re-fetch calendar events here
    logger.info(f"[Webhook] Google Calendar notification: state={resource_state}")
    return {"received": True}


@router.post("/webhooks/teams")
async def teams_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Microsoft Teams change notifications."""
    body = await request.json()

    # Teams validation challenge
    if "validationToken" in body:
        return body["validationToken"]

    _audit(db, None, "microsoft_teams", AuditAction.WEBHOOK_RECEIVED,
           details={"notifications": len(body.get("value", []))})

    return {"received": True}

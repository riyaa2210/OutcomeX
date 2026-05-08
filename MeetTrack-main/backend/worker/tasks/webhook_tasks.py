"""
Webhook Tasks
=============
Celery tasks for reliable webhook delivery to Activepieces.

Tasks:
  - webhook_delivery_task       : deliver meeting payload with retry
  - retry_dead_letter_webhooks  : periodic sweep of failed webhooks (Beat)

Retry strategy: exponential backoff 30s → 60s → 120s → 240s
Dead-letter: logged to task_logs after max_retries exhausted
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import requests
from celery.exceptions import SoftTimeLimitExceeded

from backend.worker.celery_app import celery_app
from backend.worker.task_logger import (
    get_db, make_idempotency_key, is_duplicate,
    create_log, mark_processing, mark_completed, mark_failed, mark_dead_letter,
)
from backend.models.webhook_log import WebhookLog

logger = logging.getLogger(__name__)

WEBHOOK_URL  = os.getenv("ACTIVEPIECES_WEBHOOK_URL", "")
SECRET       = os.getenv("ACTIVEPIECES_SECRET", "")
TIMEOUT      = int(os.getenv("AUTOMATION_TIMEOUT", "10"))


def _sign(body: bytes) -> str:
    if not SECRET:
        return ""
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@celery_app.task(
    name="backend.worker.tasks.webhook_tasks.webhook_delivery_task",
    bind=True,
    max_retries=4,
    default_retry_delay=30,
    queue="webhooks",
    acks_late=True,
    soft_time_limit=60,
    time_limit=90,
)
def webhook_delivery_task(
    self,
    meeting_id: int,
    transcript: str,
    structured: dict,
    event_type: str = "meeting_processed",
):
    """
    Deliver meeting payload to Activepieces webhook with retry + idempotency.

    Args:
        meeting_id  : meeting DB id
        transcript  : raw transcript text
        structured  : {summary, decisions, action_items}
        event_type  : event label string
    """
    if not WEBHOOK_URL:
        logger.warning("[Webhook] ACTIVEPIECES_WEBHOOK_URL not set — skipping")
        return {"skipped": True, "reason": "no webhook url"}

    idem_key = make_idempotency_key("webhook", meeting_id, event_type)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            logger.info(f"[Webhook] Duplicate skipped: meeting={meeting_id}")
            return {"meeting_id": meeting_id, "skipped": True}

        log = create_log(
            db,
            task_type       = "webhook",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            input_summary   = f"event={event_type}",
            max_attempts    = self.max_retries + 1,
        )
        mark_processing(db, log)

        # ── Build payload ─────────────────────────────────────────────────
        payload = {
            "event":        event_type,
            "meeting_id":   meeting_id,
            "meeting_text": transcript[:500],  # truncate for webhook
            "summary":      structured.get("summary", ""),
            "decisions":    structured.get("decisions", []),
            "action_items": structured.get("action_items", []),
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "version":      "2.0",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        sig  = _sign(body)

        headers = {
            "Content-Type": "application/json",
            "X-Source":     "outcomex-celery",
            "X-Signature":  sig,
            "X-Meeting-Id": str(meeting_id),
        }

        # ── Deliver ───────────────────────────────────────────────────────
        resp = requests.post(WEBHOOK_URL, data=body, headers=headers, timeout=TIMEOUT)

        # ── Audit log ─────────────────────────────────────────────────────
        wh_log = db.query(WebhookLog).filter(
            WebhookLog.meeting_id == meeting_id,
            WebhookLog.event_type == event_type,
        ).first()
        if not wh_log:
            wh_log = WebhookLog(
                meeting_id      = meeting_id,
                event_type      = event_type,
                idempotency_key = idem_key,
                status          = "pending",
                attempt_count   = 0,
                max_attempts    = self.max_retries + 1,
            )
            db.add(wh_log)

        wh_log.attempt_count     += 1
        wh_log.last_attempted_at  = datetime.now(timezone.utc)
        wh_log.n8n_status_code    = resp.status_code
        wh_log.n8n_response       = resp.text[:2000]

        if resp.ok:
            wh_log.status       = "delivered"
            wh_log.delivered_at = datetime.now(timezone.utc)
            db.commit()
            mark_completed(db, log, f"http={resp.status_code}")
            logger.info(f"[Webhook] ✅ Delivered meeting={meeting_id} status={resp.status_code}")
            return {"meeting_id": meeting_id, "status_code": resp.status_code}

        # Non-2xx — retry
        wh_log.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        db.commit()
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    except SoftTimeLimitExceeded:
        mark_failed(db, log, Exception("Soft time limit"), retrying=False)
        raise

    except requests.exceptions.Timeout:
        exc = RuntimeError(f"Timeout after {TIMEOUT}s")
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"error": str(exc), "dead_letter": True}

    except requests.exceptions.ConnectionError as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"error": str(exc), "dead_letter": True}

    except Exception as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"error": str(exc), "dead_letter": True}

    finally:
        db.close()


@celery_app.task(
    name="backend.worker.tasks.webhook_tasks.retry_dead_letter_webhooks",
    queue="webhooks",
    soft_time_limit=120,
    time_limit=180,
)
def retry_dead_letter_webhooks():
    """
    Periodic task (Celery Beat): re-queue failed webhook deliveries.
    Runs every 10 minutes. Picks up to 20 failed webhooks.
    """
    from sqlalchemy import text as sql_text
    db = get_db()

    try:
        failed = db.execute(sql_text("""
            SELECT meeting_id, event_type
            FROM webhook_logs
            WHERE status = 'failed'
              AND attempt_count < max_attempts
            ORDER BY last_attempted_at ASC
            LIMIT 20
        """)).fetchall()

        requeued = 0
        for row in failed:
            # Fetch meeting data to re-deliver
            from backend.models.meeting import Meeting
            from backend.models.result import Result
            meeting = db.query(Meeting).filter(Meeting.id == row.meeting_id).first()
            if not meeting:
                continue

            result = db.query(Result).filter(Result.meeting_id == row.meeting_id).first()
            structured = {}
            if result and result.summary:
                try:
                    structured = json.loads(result.summary)
                except Exception:
                    pass

            # Reset idempotency so it can be re-delivered
            from backend.models.task_log import TaskLog, TaskState
            idem_key = make_idempotency_key("webhook", row.meeting_id, row.event_type)
            tlog = db.query(TaskLog).filter(TaskLog.idempotency_key == idem_key).first()
            if tlog:
                tlog.state = TaskState.QUEUED
                db.commit()

            webhook_delivery_task.apply_async(
                args=[row.meeting_id, meeting.transcript or "", structured, row.event_type],
                queue="webhooks",
            )
            requeued += 1

        logger.info(f"[Webhook] Dead-letter sweep: requeued {requeued} webhooks")
        return {"requeued": requeued}

    finally:
        db.close()

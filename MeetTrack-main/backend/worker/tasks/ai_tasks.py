"""
AI Extraction Tasks
===================
Celery tasks for AI-powered meeting analysis.

Task: ai_extraction_task
  - Runs NLP pre-processing + Gemini structured extraction
  - Persists summary, decisions, action items
  - Chains into webhook_task + rag_index_task + email_task
  - Exponential backoff: 30s → 60s → 120s (API rate limits)
"""

import json
import logging
from datetime import datetime

from celery.exceptions import SoftTimeLimitExceeded

from backend.worker.celery_app import celery_app
from backend.worker.task_logger import (
    get_db, make_idempotency_key, is_duplicate,
    create_log, mark_processing, mark_completed, mark_failed, mark_dead_letter,
)
from backend.models.meeting import Meeting
from backend.models.action_item import ActionItem

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.worker.tasks.ai_tasks.ai_extraction_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_extraction",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=300,
)
def ai_extraction_task(self, meeting_id: int, user_id: int):
    """
    Run the full AI extraction pipeline on a meeting transcript.

    Args:
        meeting_id : DB id of the Meeting row (must have transcript set)
        user_id    : owner user id

    Returns:
        {"meeting_id": int, "action_items": int, "decisions": int}
    """
    idem_key = make_idempotency_key("ai_extraction", meeting_id)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            logger.info(f"[AI] Duplicate skipped: meeting={meeting_id}")
            return {"meeting_id": meeting_id, "skipped": True}

        log = create_log(
            db,
            task_type       = "ai_extraction",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            user_id         = user_id,
            input_summary   = f"meeting_id={meeting_id}",
            max_attempts    = self.max_retries + 1,
        )
        mark_processing(db, log)

        # ── Fetch meeting ─────────────────────────────────────────────────
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")
        if not meeting.transcript:
            raise ValueError(f"Meeting {meeting_id} has no transcript yet")

        transcript = meeting.transcript

        # ── AI extraction ─────────────────────────────────────────────────
        from backend.services.summary_service import generate_structured_summary
        logger.info(f"[AI] Running extraction for meeting={meeting_id}")
        structured = generate_structured_summary(transcript)

        # ── Persist action items (with transaction rollback on failure) ───
        saved_items = []
        try:
            # Remove old action items for this meeting (re-process case)
            db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).delete()

            for item in structured.get("action_items", []):
                if item.get("confidence_score", 1.0) < 0.4:
                    continue
                action = ActionItem(
                    meeting_id  = meeting_id,
                    assigned_to = item.get("assignee") or "Unassigned",
                    title       = item.get("task", "")[:100],
                    description = item.get("task", ""),
                    deadline    = item.get("deadline"),
                    status      = "Pending",
                )
                db.add(action)
                saved_items.append({
                    "task":             item.get("task"),
                    "assignee":         item.get("assignee"),
                    "deadline":         item.get("deadline"),
                    "confidence_score": item.get("confidence_score"),
                })

            db.commit()
            logger.info(f"[AI] Saved {len(saved_items)} action items for meeting={meeting_id}")

        except Exception as db_exc:
            db.rollback()
            raise RuntimeError(f"DB transaction failed: {db_exc}") from db_exc

        # ── Chain downstream tasks ────────────────────────────────────────
        payload = {
            "summary":      structured.get("summary", ""),
            "decisions":    structured.get("decisions", []),
            "action_items": saved_items,
        }

        # Webhook notification
        from backend.worker.tasks.webhook_tasks import webhook_delivery_task
        webhook_delivery_task.apply_async(
            args=[meeting_id, transcript, payload],
            queue="webhooks",
        )

        # RAG indexing
        from backend.worker.tasks.ai_tasks import rag_index_task
        rag_index_task.apply_async(
            args=[meeting_id, user_id, transcript, meeting.title or "", payload["summary"], payload["decisions"]],
            queue="ai_extraction",
        )

        # Email notifications for assigned tasks
        if saved_items:
            from backend.worker.tasks.email_tasks import send_task_assignment_emails
            send_task_assignment_emails.apply_async(
                args=[meeting_id, meeting.title or "Meeting", saved_items],
                queue="email_delivery",
            )

        mark_completed(
            db, log,
            f"action_items={len(saved_items)} decisions={len(structured.get('decisions', []))}"
        )

        return {
            "meeting_id":   meeting_id,
            "action_items": len(saved_items),
            "decisions":    len(structured.get("decisions", [])),
        }

    except SoftTimeLimitExceeded:
        mark_failed(db, log, Exception("Soft time limit exceeded"), retrying=False)
        raise

    except Exception as exc:
        attempt = self.request.retries + 1
        logger.warning(f"[AI] Attempt {attempt} failed for meeting={meeting_id}: {exc}")

        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            delay = 30 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=delay)

        mark_dead_letter(db, log, str(exc))
        logger.error(f"[AI] ❌ Dead letter: meeting={meeting_id} — {exc}")
        return {"meeting_id": meeting_id, "error": str(exc), "dead_letter": True}

    finally:
        db.close()


@celery_app.task(
    name="backend.worker.tasks.ai_tasks.rag_index_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="ai_extraction",
    acks_late=True,
    soft_time_limit=120,
    time_limit=180,
)
def rag_index_task(
    self,
    meeting_id: int,
    user_id: int,
    transcript: str,
    title: str,
    summary: str,
    decisions: list,
):
    """Index meeting chunks into pgvector for RAG search."""
    idem_key = make_idempotency_key("rag_index", meeting_id)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            return {"meeting_id": meeting_id, "skipped": True}

        log = create_log(
            db,
            task_type       = "rag_index",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            user_id         = user_id,
            input_summary   = f"meeting_id={meeting_id}",
        )
        mark_processing(db, log)

        from backend.services.rag_service import index_meeting
        chunks = index_meeting(db, meeting_id, user_id, transcript, title, summary, decisions)

        mark_completed(db, log, f"chunks={chunks}")
        return {"meeting_id": meeting_id, "chunks_indexed": chunks}

    except Exception as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"meeting_id": meeting_id, "error": str(exc)}

    finally:
        db.close()

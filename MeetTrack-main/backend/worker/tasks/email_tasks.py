"""
Email Delivery Tasks
====================
Celery tasks for sending email notifications.

Tasks:
  - send_task_assignment_emails : notify assignees of new action items
  - send_meeting_summary_email  : send full meeting summary to organiser
  - send_overdue_reminder_email : daily digest of overdue tasks

Retry: 3 attempts, 15s → 30s → 60s backoff (SMTP transient errors)
"""

import logging
import os
from typing import Optional

from celery.exceptions import SoftTimeLimitExceeded

from backend.worker.celery_app import celery_app
from backend.worker.task_logger import (
    get_db, make_idempotency_key, is_duplicate,
    create_log, mark_processing, mark_completed, mark_failed, mark_dead_letter,
)

logger = logging.getLogger(__name__)


def _send_via_sns(subject: str, message: str) -> bool:
    """Send via AWS SNS (existing notification service)."""
    try:
        from backend.services.notification_service import send_email_notification
        send_email_notification(subject=subject, message=message)
        return True
    except Exception as exc:
        logger.warning(f"[Email] SNS send failed: {exc}")
        return False


@celery_app.task(
    name="backend.worker.tasks.email_tasks.send_task_assignment_emails",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    queue="email_delivery",
    acks_late=True,
    soft_time_limit=60,
    time_limit=90,
)
def send_task_assignment_emails(
    self,
    meeting_id: int,
    meeting_title: str,
    action_items: list,
):
    """
    Send email notifications to each unique assignee.

    Args:
        meeting_id    : meeting DB id
        meeting_title : human-readable meeting title
        action_items  : list of {task, assignee, deadline, confidence_score}
    """
    idem_key = make_idempotency_key("email_assignment", meeting_id)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            return {"meeting_id": meeting_id, "skipped": True}

        log = create_log(
            db,
            task_type       = "email_delivery",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            input_summary   = f"items={len(action_items)}",
        )
        mark_processing(db, log)

        # Group tasks by assignee
        by_assignee: dict[str, list] = {}
        for item in action_items:
            name = item.get("assignee") or "Unassigned"
            if name == "Unassigned":
                continue
            by_assignee.setdefault(name, []).append(item)

        sent_count = 0
        for assignee, tasks in by_assignee.items():
            task_lines = "\n".join(
                f"  • {t['task']}"
                + (f" (due {t['deadline']})" if t.get("deadline") else "")
                for t in tasks
            )
            subject = f"[OutcomeX] New tasks assigned to you — {meeting_title}"
            message = (
                f"Hi {assignee},\n\n"
                f"You have {len(tasks)} new action item(s) from the meeting '{meeting_title}':\n\n"
                f"{task_lines}\n\n"
                f"Log in to OutcomeX to view details and update status.\n\n"
                f"— OutcomeX AI"
            )
            if _send_via_sns(subject, message):
                sent_count += 1
                logger.info(f"[Email] Sent assignment email for {assignee}")

        mark_completed(db, log, f"sent={sent_count} assignees={len(by_assignee)}")
        return {"meeting_id": meeting_id, "emails_sent": sent_count}

    except SoftTimeLimitExceeded:
        mark_failed(db, log, Exception("Soft time limit"), retrying=False)
        raise

    except Exception as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=15 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"meeting_id": meeting_id, "error": str(exc)}

    finally:
        db.close()


@celery_app.task(
    name="backend.worker.tasks.email_tasks.send_meeting_summary_email",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    queue="email_delivery",
    acks_late=True,
    soft_time_limit=60,
    time_limit=90,
)
def send_meeting_summary_email(
    self,
    meeting_id: int,
    user_email: str,
    meeting_title: str,
    summary: str,
    decisions: list,
    action_items: list,
):
    """Send the full meeting summary to the meeting organiser."""
    idem_key = make_idempotency_key("email_summary", meeting_id, user_email)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            return {"skipped": True}

        log = create_log(
            db,
            task_type       = "email_delivery",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            input_summary   = f"to={user_email}",
        )
        mark_processing(db, log)

        decisions_text = "\n".join(f"  • {d}" for d in decisions) or "  None recorded"
        actions_text   = "\n".join(
            f"  • {a['task']} → {a.get('assignee','?')}"
            + (f" (due {a['deadline']})" if a.get("deadline") else "")
            for a in action_items
        ) or "  None recorded"

        subject = f"[OutcomeX] Meeting Summary — {meeting_title}"
        message = (
            f"Meeting: {meeting_title}\n\n"
            f"SUMMARY\n{summary}\n\n"
            f"DECISIONS\n{decisions_text}\n\n"
            f"ACTION ITEMS\n{actions_text}\n\n"
            f"— OutcomeX AI"
        )

        success = _send_via_sns(subject, message)
        mark_completed(db, log, f"sent={success}")
        return {"meeting_id": meeting_id, "sent": success}

    except Exception as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=15 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"error": str(exc)}

    finally:
        db.close()


@celery_app.task(
    name="backend.worker.tasks.email_tasks.send_overdue_reminder_email",
    bind=True,
    max_retries=2,
    queue="email_delivery",
    soft_time_limit=120,
    time_limit=180,
)
def send_overdue_reminder_email(self, user_id: int, user_email: str):
    """Send a digest of overdue tasks to a user. Called by Celery Beat."""
    from sqlalchemy import text as sql_text
    db = get_db()

    try:
        rows = db.execute(sql_text("""
            SELECT ai.description, ai.assigned_to, ai.deadline, m.title
            FROM action_items ai
            JOIN meetings m ON ai.meeting_id = m.id
            WHERE m.user_id = :uid
              AND ai.deadline IS NOT NULL
              AND LOWER(ai.status) NOT IN ('completed','done')
            ORDER BY ai.deadline ASC
            LIMIT 20
        """), {"uid": user_id}).fetchall()

        if not rows:
            return {"user_id": user_id, "overdue": 0}

        lines = "\n".join(
            f"  • [{r.title}] {r.description} → {r.assigned_to} (due {r.deadline})"
            for r in rows
        )
        subject = f"[OutcomeX] You have {len(rows)} overdue task(s)"
        message = f"Hi,\n\nThe following tasks are overdue:\n\n{lines}\n\n— OutcomeX AI"
        _send_via_sns(subject, message)

        return {"user_id": user_id, "overdue": len(rows)}

    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30)
        return {"error": str(exc)}

    finally:
        db.close()

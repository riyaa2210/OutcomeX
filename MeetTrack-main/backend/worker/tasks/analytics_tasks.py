"""
Analytics Tasks
===============
Celery tasks for background analytics computation.

Tasks:
  - compute_analytics_task  : pre-compute and cache analytics for a user
  - cleanup_old_task_logs   : daily cleanup of task_logs older than 30 days (Beat)
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from backend.worker.celery_app import celery_app
from backend.worker.task_logger import (
    get_db, make_idempotency_key, is_duplicate,
    create_log, mark_processing, mark_completed, mark_failed, mark_dead_letter,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.worker.tasks.analytics_tasks.compute_analytics_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="analytics",
    acks_late=True,
    soft_time_limit=180,
    time_limit=240,
)
def compute_analytics_task(self, user_id: int, days: int = 30):
    """
    Pre-compute analytics insights for a user and cache in DB.

    Args:
        user_id : user to compute analytics for
        days    : lookback window in days
    """
    idem_key = make_idempotency_key("analytics", user_id, days)
    db = get_db()

    try:
        dup = is_duplicate(db, idem_key)
        if dup:
            return {"user_id": user_id, "skipped": True}

        log = create_log(
            db,
            task_type       = "analytics",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            user_id         = user_id,
            input_summary   = f"days={days}",
        )
        mark_processing(db, log)

        since = datetime.now(timezone.utc) - timedelta(days=days)

        import asyncio
        from backend.services.analytics_service import compute_ai_insights
        insights = asyncio.run(compute_ai_insights(db, user_id, since))

        mark_completed(db, log, f"efficiency={insights.get('efficiency', {}).get('score', 0)}")
        return {"user_id": user_id, "insights": insights}

    except Exception as exc:
        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        mark_dead_letter(db, log, str(exc))
        return {"user_id": user_id, "error": str(exc)}

    finally:
        db.close()


@celery_app.task(
    name="backend.worker.tasks.analytics_tasks.cleanup_old_task_logs",
    queue="analytics",
    soft_time_limit=60,
    time_limit=90,
)
def cleanup_old_task_logs():
    """
    Periodic task (Celery Beat): delete task_logs older than 30 days.
    Keeps the table lean and queries fast.
    """
    from sqlalchemy import text as sql_text
    db = get_db()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = db.execute(sql_text("""
            DELETE FROM task_logs
            WHERE created_at < :cutoff
              AND state IN ('completed', 'failed')
        """), {"cutoff": cutoff})
        db.commit()
        deleted = result.rowcount
        logger.info(f"[Analytics] Cleaned up {deleted} old task logs")
        return {"deleted": deleted}

    finally:
        db.close()

"""
Transcription Tasks
===================
Celery tasks for audio transcription via Colab Whisper API.

Task: transcribe_audio_task
  - Sends audio file to Colab Whisper endpoint
  - Stores transcript in Meeting.transcript
  - Chains into ai_extraction_task on success
  - Exponential backoff: 60s → 120s → 240s (network issues)
  - Dead-letter after 3 failures
"""

import logging
import traceback
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from backend.worker.celery_app import celery_app
from backend.worker.task_logger import (
    get_db, make_idempotency_key, is_duplicate,
    create_log, mark_processing, mark_completed, mark_failed, mark_dead_letter,
)
from backend.models.meeting import Meeting

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.worker.tasks.transcription_tasks.transcribe_audio_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="transcription",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=290,
    time_limit=350,
)
def transcribe_audio_task(self, meeting_id: int, file_path: str, user_id: int):
    """
    Transcribe an audio file and store the result.

    Args:
        meeting_id : DB id of the Meeting row
        file_path  : absolute path to the audio file on disk
        user_id    : owner user id (for logging)

    Returns:
        {"meeting_id": int, "transcript_length": int}
    """
    idem_key = make_idempotency_key("transcription", meeting_id, file_path)
    db = get_db()

    try:
        # ── Idempotency check ──────────────────────────────────────────────
        dup = is_duplicate(db, idem_key)
        if dup:
            logger.info(f"[Transcription] Duplicate skipped: meeting={meeting_id}")
            return {"meeting_id": meeting_id, "skipped": True}

        # ── Create / update task log ───────────────────────────────────────
        log = create_log(
            db,
            task_type       = "transcription",
            task_name       = self.name,
            celery_task_id  = self.request.id,
            idempotency_key = idem_key,
            meeting_id      = meeting_id,
            user_id         = user_id,
            input_summary   = f"file={file_path}",
            max_attempts    = self.max_retries + 1,
        )
        mark_processing(db, log)

        # ── Transcribe ────────────────────────────────────────────────────
        from backend.services.transcribe_service import transcribe_audio
        logger.info(f"[Transcription] Starting meeting={meeting_id}")
        transcript = transcribe_audio(file_path)

        # ── Persist transcript ────────────────────────────────────────────
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found in DB")

        meeting.transcript = transcript
        db.commit()

        mark_completed(db, log, f"transcript_length={len(transcript)}")
        logger.info(f"[Transcription] ✅ meeting={meeting_id} chars={len(transcript)}")

        # ── Chain to AI extraction ────────────────────────────────────────
        from backend.worker.tasks.ai_tasks import ai_extraction_task
        ai_extraction_task.apply_async(
            args=[meeting_id, user_id],
            queue="ai_extraction",
        )

        return {"meeting_id": meeting_id, "transcript_length": len(transcript)}

    except SoftTimeLimitExceeded:
        mark_failed(db, log, Exception("Soft time limit exceeded"), retrying=False)
        raise

    except Exception as exc:
        attempt = self.request.retries + 1
        logger.warning(f"[Transcription] Attempt {attempt} failed: {exc}")

        if self.request.retries < self.max_retries:
            mark_failed(db, log, exc, retrying=True)
            # Exponential backoff: 60s, 120s, 240s
            delay = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=delay)

        # All retries exhausted → dead letter
        mark_dead_letter(db, log, str(exc))
        logger.error(f"[Transcription] ❌ Dead letter: meeting={meeting_id} — {exc}")
        return {"meeting_id": meeting_id, "error": str(exc), "dead_letter": True}

    finally:
        db.close()

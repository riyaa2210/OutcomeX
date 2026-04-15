"""
n8n Webhook Service
===================
Handles all communication from the backend to n8n with:
  - Correct payload shape matching your actual n8n workflow
  - Retry with exponential back-off (3 attempts)
  - Idempotency — one delivery per (meeting_id, event_type)
  - Full audit trail via WebhookLog
  - Graceful degradation — never crashes the main request

Your n8n Flow (top row):
  Webhook → HTTP Request POST /extract-tasks → Code JS → Execute SQL

The webhook receives our payload, then calls /extract-tasks on the backend.
So we POST directly to the n8n webhook URL with { meeting_text, meeting_id,
summary, decisions } and n8n forwards meeting_text to /extract-tasks.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.models.webhook_log import WebhookLog

load_dotenv()
logger = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────────────────
N8N_WEBHOOK_URL: str = os.getenv(
    "N8N_WEBHOOK_URL",
    "http://localhost:5678/webhook/meeting-data",
)
N8N_TIMEOUT: int     = int(os.getenv("N8N_TIMEOUT", "8"))
N8N_MAX_RETRIES: int = int(os.getenv("N8N_MAX_RETRIES", "3"))
N8N_RETRY_DELAY: float = float(os.getenv("N8N_RETRY_DELAY", "2.0"))  # seconds


# ── payload builder ───────────────────────────────────────────────────────────

def build_payload(
    meeting_id: int,
    transcript: str,
    structured: dict,
) -> dict:
    """
    Build the payload sent to n8n.

    Shape matches what your n8n HTTP Request node expects:
      - meeting_text  → forwarded to POST /extract-tasks
      - meeting_id    → stored in SQL
      - summary       → stored / emailed
      - decisions     → stored / emailed
      - action_items  → stored / emailed
    """
    return {
        "meeting_id":   meeting_id,
        "meeting_text": transcript,          # n8n forwards this to /extract-tasks
        "summary":      structured.get("summary", ""),
        "decisions":    structured.get("decisions", []),
        "action_items": structured.get("action_items", []),
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


# ── idempotency key ───────────────────────────────────────────────────────────

def _make_idempotency_key(meeting_id: int, event_type: str) -> str:
    """
    SHA-256 of meeting_id + event_type.
    One delivery per (meeting, event) — prevents duplicate n8n triggers
    on retries or accidental double-calls.
    """
    raw = f"{meeting_id}:{event_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── core delivery ─────────────────────────────────────────────────────────────

def _attempt_delivery(payload: dict) -> tuple[int, str]:
    """
    Single HTTP POST attempt to n8n.
    Returns (status_code, response_body_snippet).
    Raises requests.RequestException on network failure.
    """
    resp = requests.post(
        N8N_WEBHOOK_URL,
        json=payload,
        timeout=N8N_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    body = resp.text[:2000]  # cap stored response
    return resp.status_code, body


# ── public API ────────────────────────────────────────────────────────────────

def trigger_n8n_workflow(
    db: Session,
    meeting_id: int,
    transcript: str,
    structured: dict,
    event_type: str = "meeting_processed",
) -> Optional[WebhookLog]:
    """
    Trigger the n8n webhook with retry + idempotency + audit logging.

    Called as a FastAPI BackgroundTask — never raises, never blocks the response.

    Returns the WebhookLog row (useful for tests / admin endpoints).
    """
    idem_key = _make_idempotency_key(meeting_id, event_type)

    # ── idempotency check ──────────────────────────────────────────────────
    existing = db.query(WebhookLog).filter(
        WebhookLog.idempotency_key == idem_key
    ).first()

    if existing and existing.status == "delivered":
        logger.info(
            f"[n8n] Skipping duplicate trigger for meeting={meeting_id} "
            f"event={event_type} (already delivered)"
        )
        return existing

    # ── create or reuse log row ────────────────────────────────────────────
    if existing:
        log = existing
    else:
        log = WebhookLog(
            meeting_id=meeting_id,
            event_type=event_type,
            idempotency_key=idem_key,
            status="pending",
            attempt_count=0,
            max_attempts=N8N_MAX_RETRIES,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

    payload = build_payload(meeting_id, transcript, structured)

    # ── retry loop ─────────────────────────────────────────────────────────
    for attempt in range(1, N8N_MAX_RETRIES + 1):
        log.attempt_count = attempt
        log.last_attempted_at = datetime.now(timezone.utc)
        db.commit()

        try:
            logger.info(
                f"[n8n] Attempt {attempt}/{N8N_MAX_RETRIES} "
                f"→ {N8N_WEBHOOK_URL} (meeting={meeting_id})"
            )
            status_code, body = _attempt_delivery(payload)

            log.n8n_status_code = status_code
            log.n8n_response    = body

            if 200 <= status_code < 300:
                log.status       = "delivered"
                log.delivered_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    f"[n8n] ✅ Delivered meeting={meeting_id} "
                    f"on attempt {attempt} (HTTP {status_code})"
                )
                return log

            # n8n returned a non-2xx — treat as soft failure, retry
            log.last_error = f"HTTP {status_code}: {body[:300]}"
            logger.warning(
                f"[n8n] ⚠️  HTTP {status_code} on attempt {attempt} "
                f"for meeting={meeting_id}"
            )

        except requests.exceptions.ConnectionError:
            log.last_error = "n8n unreachable (ConnectionError)"
            logger.warning(
                f"[n8n] ⚠️  n8n unreachable on attempt {attempt} "
                f"for meeting={meeting_id} — is n8n running on port 5678?"
            )
        except requests.exceptions.Timeout:
            log.last_error = f"Timeout after {N8N_TIMEOUT}s"
            logger.warning(
                f"[n8n] ⚠️  Timeout on attempt {attempt} for meeting={meeting_id}"
            )
        except Exception as exc:
            log.last_error = str(exc)[:500]
            logger.error(
                f"[n8n] ❌ Unexpected error on attempt {attempt}: {exc}"
            )

        db.commit()

        # back-off before next attempt (skip delay after last attempt)
        if attempt < N8N_MAX_RETRIES:
            delay = N8N_RETRY_DELAY * (2 ** (attempt - 1))  # 2s, 4s, 8s
            logger.info(f"[n8n] Retrying in {delay:.1f}s…")
            time.sleep(delay)

    # ── all attempts exhausted ─────────────────────────────────────────────
    log.status = "failed"
    db.commit()
    logger.error(
        f"[n8n] ❌ All {N8N_MAX_RETRIES} attempts failed for meeting={meeting_id}. "
        f"Last error: {log.last_error}"
    )
    return log


# ── health check (used by webhook_routes) ────────────────────────────────────

def ping_n8n() -> dict:
    """
    Quick connectivity check — does not trigger any workflow.
    Returns {"reachable": bool, "url": str, "error": str|None}
    """
    try:
        # HEAD request to the base n8n URL (port only, no webhook path)
        base = N8N_WEBHOOK_URL.split("/webhook")[0]
        requests.get(base, timeout=3)
        return {"reachable": True, "url": N8N_WEBHOOK_URL, "error": None}
    except Exception as exc:
        return {"reachable": False, "url": N8N_WEBHOOK_URL, "error": str(exc)}

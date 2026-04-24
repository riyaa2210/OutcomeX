"""
Automation Service — Activepieces Integration
=============================================
Replaces n8n_service.py completely.

Features:
  - HMAC-SHA256 webhook signature for security
  - SHA-256 idempotency key (one delivery per meeting+event)
  - Exponential backoff retry: 2s → 4s → 8s
  - Full audit trail via WebhookLog model
  - Graceful degradation — never crashes the main request
  - Works with Activepieces OR any webhook receiver

Environment variables:
  ACTIVEPIECES_WEBHOOK_URL   — your Activepieces flow webhook URL
  ACTIVEPIECES_SECRET        — shared secret for HMAC signature
  AUTOMATION_TIMEOUT         — request timeout in seconds (default: 10)
  AUTOMATION_MAX_RETRIES     — max retry attempts (default: 3)
  AUTOMATION_RETRY_DELAY     — base delay in seconds (default: 2.0)
"""

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from backend.models.webhook_log import WebhookLog

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
WEBHOOK_URL: str     = os.getenv("ACTIVEPIECES_WEBHOOK_URL", "")
SECRET: str          = os.getenv("ACTIVEPIECES_SECRET", "")
TIMEOUT: int         = int(os.getenv("AUTOMATION_TIMEOUT", "10"))
MAX_RETRIES: int     = int(os.getenv("AUTOMATION_MAX_RETRIES", "3"))
RETRY_DELAY: float   = float(os.getenv("AUTOMATION_RETRY_DELAY", "2.0"))


# ── Payload builder ───────────────────────────────────────────────────────────

def build_payload(meeting_id: int, transcript: str, structured: dict) -> dict:
    """
    Canonical payload shape sent to Activepieces.
    Matches the input schema expected by the flow's Code piece.
    """
    return {
        "event":        "meeting_processed",
        "meeting_id":   meeting_id,
        "meeting_text": transcript,
        "summary":      structured.get("summary", ""),
        "decisions":    structured.get("decisions", []),
        "action_items": structured.get("action_items", []),
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "version":      "2.0",
    }


# ── Idempotency key ───────────────────────────────────────────────────────────

def _idempotency_key(meeting_id: int, event_type: str) -> str:
    """SHA-256 of meeting_id:event_type — one delivery per (meeting, event)."""
    return hashlib.sha256(f"{meeting_id}:{event_type}".encode()).hexdigest()


# ── HMAC signature ────────────────────────────────────────────────────────────

def _sign_payload(payload_bytes: bytes) -> str:
    """
    HMAC-SHA256 signature of the raw JSON body.
    Activepieces flow verifies this in the first Code piece.
    Header: X-Signature: sha256=<hex>
    """
    if not SECRET:
        return ""
    sig = hmac.new(SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ── Single delivery attempt ───────────────────────────────────────────────────

def _attempt(payload: dict) -> tuple[int, str]:
    """POST to Activepieces. Returns (status_code, body_snippet)."""
    body_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature  = _sign_payload(body_bytes)

    headers = {
        "Content-Type":  "application/json",
        "X-Source":      "outcomex-backend",
        "X-Signature":   signature,
        "X-Meeting-Id":  str(payload.get("meeting_id", "")),
    }

    resp = requests.post(
        WEBHOOK_URL,
        data=body_bytes,
        headers=headers,
        timeout=TIMEOUT,
    )
    return resp.status_code, resp.text[:2000]


# ── Public trigger function ───────────────────────────────────────────────────

def trigger_automation(
    db: Session,
    meeting_id: int,
    transcript: str,
    structured: dict,
    event_type: str = "meeting_processed",
) -> Optional[WebhookLog]:
    """
    Send meeting data to Activepieces with retry + idempotency + audit log.

    Called as a FastAPI BackgroundTask — never raises, never blocks response.
    Drop-in replacement for trigger_n8n_workflow().
    """
    if not WEBHOOK_URL:
        logger.warning("[Automation] ACTIVEPIECES_WEBHOOK_URL not set — skipping")
        return None

    idem_key = _idempotency_key(meeting_id, event_type)

    # ── Idempotency check ──────────────────────────────────────────────────
    existing = db.query(WebhookLog).filter(
        WebhookLog.idempotency_key == idem_key
    ).first()

    if existing and existing.status == "delivered":
        logger.info(f"[Automation] Skipping duplicate: meeting={meeting_id} already delivered")
        return existing

    # ── Create or reuse log row ────────────────────────────────────────────
    log = existing or WebhookLog(
        meeting_id=meeting_id,
        event_type=event_type,
        idempotency_key=idem_key,
        status="pending",
        attempt_count=0,
        max_attempts=MAX_RETRIES,
    )
    if not existing:
        db.add(log)
        db.commit()
        db.refresh(log)

    payload = build_payload(meeting_id, transcript, structured)

    # ── Retry loop with exponential backoff ────────────────────────────────
    for attempt in range(1, MAX_RETRIES + 1):
        log.attempt_count      = attempt
        log.last_attempted_at  = datetime.now(timezone.utc)
        db.commit()

        try:
            logger.info(f"[Automation] Attempt {attempt}/{MAX_RETRIES} → {WEBHOOK_URL}")
            status_code, body = _attempt(payload)

            log.n8n_status_code = status_code   # reuse existing column
            log.n8n_response    = body

            if 200 <= status_code < 300:
                log.status       = "delivered"
                log.delivered_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[Automation] ✅ Delivered meeting={meeting_id} attempt={attempt}")
                return log

            log.last_error = f"HTTP {status_code}: {body[:300]}"
            logger.warning(f"[Automation] HTTP {status_code} on attempt {attempt}")

        except requests.exceptions.ConnectionError:
            log.last_error = "Connection refused — is Activepieces running?"
            logger.warning(f"[Automation] Connection error on attempt {attempt}")
        except requests.exceptions.Timeout:
            log.last_error = f"Timeout after {TIMEOUT}s"
            logger.warning(f"[Automation] Timeout on attempt {attempt}")
        except Exception as exc:
            log.last_error = str(exc)[:500]
            logger.error(f"[Automation] Unexpected error: {exc}")

        db.commit()

        # Exponential backoff: 2s, 4s, 8s
        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            logger.info(f"[Automation] Retrying in {delay:.0f}s…")
            time.sleep(delay)

    log.status = "failed"
    db.commit()
    logger.error(f"[Automation] ❌ All {MAX_RETRIES} attempts failed for meeting={meeting_id}")
    return log


# ── Health check ──────────────────────────────────────────────────────────────

def ping_automation() -> dict:
    """Check if Activepieces webhook URL is reachable."""
    if not WEBHOOK_URL:
        return {"reachable": False, "url": "", "error": "ACTIVEPIECES_WEBHOOK_URL not set"}
    try:
        base = WEBHOOK_URL.split("/api/")[0] if "/api/" in WEBHOOK_URL else WEBHOOK_URL
        requests.get(base, timeout=3)
        return {"reachable": True, "url": WEBHOOK_URL, "error": None}
    except Exception as exc:
        return {"reachable": False, "url": WEBHOOK_URL, "error": str(exc)}

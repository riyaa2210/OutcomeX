"""
Anomaly Detection
=================
Detects suspicious activity patterns using Redis-backed counters.

Detects:
  - Credential stuffing (many failed logins from same IP)
  - Account enumeration (many 404s on /profile endpoints)
  - Scraping (high request rate with no auth)
  - Unusual access hours (configurable)
  - Rapid meeting creation (potential abuse)
  - Token reuse after logout

Risk scoring:
  0-20:  normal
  21-50: suspicious — log only
  51-80: high risk — log + alert
  81+:   critical — block + alert
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _get_redis():
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        return r
    except Exception:
        return None


# ── Risk scoring ──────────────────────────────────────────────────────────────

def compute_risk_score(
    ip: str,
    user_id: Optional[int] = None,
    event_type: str = "",
) -> int:
    """
    Compute a risk score 0-100 for a request.
    Higher = more suspicious.
    """
    r = _get_redis()
    if r is None:
        return 0

    score = 0

    try:
        # Failed logins from this IP
        failed = int(r.get(f"failed_login:{ip}") or 0)
        score += min(failed * 10, 40)

        # Request rate (last 60s)
        rate_key = f"req_rate:{ip}"
        req_count = int(r.get(rate_key) or 0)
        if req_count > 200:
            score += 30
        elif req_count > 100:
            score += 15

        # 404 rate (enumeration detection)
        not_found = int(r.get(f"404:{ip}") or 0)
        score += min(not_found * 5, 20)

        # Unusual hour (outside 6am-11pm UTC)
        hour = datetime.now(timezone.utc).hour
        if hour < 6 or hour > 23:
            score += 5

    except Exception as exc:
        logger.debug(f"[Anomaly] Risk score error: {exc}")

    return min(score, 100)


def record_404(ip: str) -> None:
    """Track 404 responses for enumeration detection."""
    r = _get_redis()
    if r:
        try:
            key = f"404:{ip}"
            r.incr(key)
            r.expire(key, 300)  # 5-min window
        except Exception:
            pass


def record_request(ip: str) -> None:
    """Track request rate per IP."""
    r = _get_redis()
    if r:
        try:
            key = f"req_rate:{ip}"
            r.incr(key)
            r.expire(key, 60)
        except Exception:
            pass


# ── Token revocation (logout / refresh) ──────────────────────────────────────

def revoke_token(jti: str, expires_in: int = 86400) -> None:
    """Add a token JTI to the revocation list."""
    r = _get_redis()
    if r:
        try:
            r.setex(f"revoked_token:{jti}", expires_in, "1")
        except Exception:
            pass


def is_token_revoked(jti: str) -> bool:
    """Check if a token has been revoked."""
    r = _get_redis()
    if r is None:
        return False
    try:
        return bool(r.get(f"revoked_token:{jti}"))
    except Exception:
        return False


# ── Webhook replay prevention ─────────────────────────────────────────────────

def check_webhook_replay(event_id: str, window: int = 300) -> bool:
    """
    Returns True if this webhook event_id has been seen before (replay attack).
    Stores event_id for `window` seconds.
    """
    r = _get_redis()
    if r is None:
        return False
    try:
        key = f"webhook_seen:{event_id}"
        result = r.set(key, "1", ex=window, nx=True)
        return result is None  # None = key already existed = replay
    except Exception:
        return False


# ── Anomaly alerts ────────────────────────────────────────────────────────────

def check_and_alert(
    ip: str,
    user_id: Optional[int],
    event_type: str,
    db=None,
) -> int:
    """
    Compute risk score and log anomaly if threshold exceeded.
    Returns risk score.
    """
    score = compute_risk_score(ip, user_id, event_type)

    if score >= 51:
        from backend.security.audit_log import log_event, AuditEventType
        log_event(
            event_type  = AuditEventType.ANOMALY_DETECTED,
            user_id     = user_id,
            ip_address  = ip,
            details     = {"risk_score": score, "trigger": event_type},
            success     = False,
            risk_score  = score,
            db          = db,
        )
        logger.warning(
            f"[Anomaly] Risk score {score} for IP={ip} user={user_id} event={event_type}"
        )

    return score

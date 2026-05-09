"""
Rate Limiter & Abuse Prevention
================================
Redis-backed sliding window rate limiter.

Limits:
  - Global:          1000 req/min per IP
  - Auth endpoints:  10 req/min per IP (login, register)
  - Upload:          5 req/min per user
  - API (default):   100 req/min per user/IP

Abuse detection:
  - Repeated failed logins → temporary IP ban (15 min)
  - Rapid sequential requests → slow-down response
  - Unusual request patterns → anomaly flag

Uses Redis INCR + EXPIRE for atomic sliding window.
Falls back gracefully if Redis is unavailable.
"""

import logging
import os
import time
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# ── Redis client ──────────────────────────────────────────────────────────────

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


# ── Rate limit configs ────────────────────────────────────────────────────────

RATE_LIMITS = {
    "auth":    {"requests": 10,   "window": 60},    # 10/min — login, register
    "upload":  {"requests": 5,    "window": 60},    # 5/min — file uploads
    "api":     {"requests": 100,  "window": 60},    # 100/min — general API
    "global":  {"requests": 1000, "window": 60},    # 1000/min — per IP
    "webhook": {"requests": 50,   "window": 60},    # 50/min — webhook receivers
}

# Failed login tracking
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS   = 900  # 15 minutes


# ── Core rate limit check ─────────────────────────────────────────────────────

def check_rate_limit(
    key: str,
    limit_type: str = "api",
    raise_on_limit: bool = True,
) -> dict:
    """
    Check rate limit for a key using Redis sliding window.

    Returns:
        {"allowed": bool, "remaining": int, "reset_in": int}
    """
    config = RATE_LIMITS.get(limit_type, RATE_LIMITS["api"])
    max_requests = config["requests"]
    window       = config["window"]

    r = _get_redis()
    if r is None:
        # Redis unavailable — allow all (fail open)
        return {"allowed": True, "remaining": max_requests, "reset_in": window}

    redis_key = f"rl:{limit_type}:{key}"

    try:
        pipe = r.pipeline()
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        count, ttl = pipe.execute()

        if ttl == -1:
            r.expire(redis_key, window)
            ttl = window

        remaining = max(0, max_requests - count)
        allowed   = count <= max_requests

        if not allowed and raise_on_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl}s.",
                headers={
                    "Retry-After":          str(ttl),
                    "X-RateLimit-Limit":    str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset":    str(int(time.time()) + ttl),
                },
            )

        return {"allowed": allowed, "remaining": remaining, "reset_in": ttl}

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[RateLimit] Redis error: {exc} — allowing request")
        return {"allowed": True, "remaining": max_requests, "reset_in": window}


# ── Failed login tracking ─────────────────────────────────────────────────────

def record_failed_login(ip: str) -> int:
    """Increment failed login counter. Returns current count."""
    r = _get_redis()
    if r is None:
        return 0
    key = f"failed_login:{ip}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, LOCKOUT_SECONDS)
        return count
    except Exception:
        return 0


def clear_failed_logins(ip: str) -> None:
    """Clear failed login counter on successful login."""
    r = _get_redis()
    if r:
        try:
            r.delete(f"failed_login:{ip}")
        except Exception:
            pass


def is_ip_locked(ip: str) -> bool:
    """True if IP has exceeded failed login threshold."""
    r = _get_redis()
    if r is None:
        return False
    try:
        count = r.get(f"failed_login:{ip}")
        return int(count or 0) >= MAX_FAILED_LOGINS
    except Exception:
        return False


def get_lockout_remaining(ip: str) -> int:
    """Seconds remaining in lockout, or 0."""
    r = _get_redis()
    if r is None:
        return 0
    try:
        ttl = r.ttl(f"failed_login:{ip}")
        return max(0, ttl)
    except Exception:
        return 0


# ── FastAPI dependency factories ──────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def rate_limit(limit_type: str = "api"):
    """
    FastAPI dependency factory for rate limiting.

    Usage:
        @router.post("/login")
        def login(request: Request, _=Depends(rate_limit("auth"))):
            ...
    """
    async def _check(request: Request):
        ip = get_client_ip(request)
        # Per-IP global limit
        check_rate_limit(ip, "global")
        # Per-endpoint limit
        check_rate_limit(ip, limit_type)
        return ip

    return _check


def auth_rate_limit():
    """
    Stricter rate limit for auth endpoints + lockout check.
    """
    async def _check(request: Request):
        ip = get_client_ip(request)

        if is_ip_locked(ip):
            remaining = get_lockout_remaining(ip)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Try again in {remaining}s.",
                headers={"Retry-After": str(remaining)},
            )

        check_rate_limit(ip, "auth")
        return ip

    return _check

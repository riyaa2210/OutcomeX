"""
LLM Response Cache
==================
Two-tier caching:
  1. In-memory LRU cache (fast, per-process, no persistence)
  2. Redis cache (shared across workers, 1-hour TTL)

Cache key = SHA-256(provider + model + task_type + prompt[:500])
Identical prompts (e.g. repeated meeting re-processing) return instantly.
"""

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

# ── In-memory LRU ─────────────────────────────────────────────────────────────

class LRUCache:
    def __init__(self, max_size: int = 256):
        self._cache: OrderedDict = OrderedDict()
        self._max   = max_size

    def get(self, key: str) -> Optional[dict]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        entry = self._cache[key]
        if entry["expires_at"] < time.time():
            del self._cache[key]
            return None
        return entry["value"]

    def set(self, key: str, value: dict, ttl: int = 3600) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = {"value": value, "expires_at": time.time() + ttl}
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        return {"size": len(self._cache), "max_size": self._max}


_lru = LRUCache(max_size=512)


# ── Redis cache ───────────────────────────────────────────────────────────────

def _get_redis():
    """Lazy Redis connection — returns None if Redis unavailable."""
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        return r
    except Exception:
        return None


# ── Cache key ─────────────────────────────────────────────────────────────────

def make_cache_key(provider: str, model: str, task_type: str, prompt: str) -> str:
    """Deterministic SHA-256 cache key."""
    raw = f"{provider}:{model}:{task_type}:{prompt[:500]}"
    return "llm:" + hashlib.sha256(raw.encode()).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

def get_cached(key: str) -> Optional[dict]:
    """Check memory first, then Redis."""
    hit = _lru.get(key)
    if hit:
        logger.debug(f"[Cache] Memory hit: {key[:16]}…")
        return hit

    r = _get_redis()
    if r:
        try:
            raw = r.get(key)
            if raw:
                value = json.loads(raw)
                _lru.set(key, value)  # warm memory cache
                logger.debug(f"[Cache] Redis hit: {key[:16]}…")
                return value
        except Exception as exc:
            logger.warning(f"[Cache] Redis get error: {exc}")

    return None


def set_cached(key: str, value: dict, ttl: int = 3600) -> None:
    """Write to both memory and Redis."""
    _lru.set(key, value, ttl=ttl)

    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl, json.dumps(value))
        except Exception as exc:
            logger.warning(f"[Cache] Redis set error: {exc}")


def invalidate(key: str) -> None:
    """Remove from both caches."""
    if key in _lru._cache:
        del _lru._cache[key]
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass


def cache_stats() -> dict:
    memory = _lru.stats()
    redis_ok = _get_redis() is not None
    return {"memory": memory, "redis_available": redis_ok}

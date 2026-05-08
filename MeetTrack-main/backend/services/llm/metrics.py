"""
LLM Metrics Store
=================
Records every LLM call to PostgreSQL for admin panel analytics.

Tracks per-provider, per-model:
  - Latency (p50, p95, p99)
  - Token usage and cost
  - Success / failure rates
  - Quality scores
  - Hallucination rates
  - Quota usage

Also maintains an in-memory rolling window for real-time dashboard.
"""

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, Index
from sqlalchemy.sql import func

from backend.app.database import Base, SessionLocal

logger = logging.getLogger(__name__)


# ── DB Model ──────────────────────────────────────────────────────────────────

class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"
    __table_args__ = (
        Index("ix_llm_provider_created", "provider", "created_at"),
        Index("ix_llm_task_type",        "task_type"),
        Index("ix_llm_created_at",       "created_at"),
        {"extend_existing": True},
    )

    id                  = Column(Integer, primary_key=True, index=True)
    provider            = Column(String(50),  nullable=False)
    model               = Column(String(100), nullable=False)
    task_type           = Column(String(50),  nullable=False)
    meeting_id          = Column(Integer,     nullable=True)
    user_id             = Column(Integer,     nullable=True)

    # Performance
    latency_ms          = Column(Float,   nullable=False)
    prompt_tokens       = Column(Integer, default=0)
    completion_tokens   = Column(Integer, default=0)
    total_tokens        = Column(Integer, default=0)
    cost_usd            = Column(Float,   default=0.0)

    # Quality
    quality_score       = Column(Float,   nullable=True)
    hallucination_risk  = Column(Float,   nullable=True)
    cache_hit           = Column(Boolean, default=False)

    # Status
    success             = Column(Boolean, default=True)
    error_type          = Column(String(100), nullable=True)
    fallback_used       = Column(Boolean, default=False)
    provider_chain      = Column(String(200), nullable=True)  # e.g. "gemini→openai→local"

    created_at          = Column(DateTime(timezone=True), server_default=func.now())


# ── In-memory rolling window (last 1000 calls per provider) ──────────────────

_rolling: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))


def _add_to_rolling(provider: str, entry: dict) -> None:
    _rolling[provider].append(entry)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * p / 100)
    return round(sorted_v[min(idx, len(sorted_v) - 1)], 1)


# ── Record a call ─────────────────────────────────────────────────────────────

def record_call(
    response,           # LLMResponse
    meeting_id: Optional[int] = None,
    user_id: Optional[int] = None,
    hallucination_risk: float = 0.0,
    fallback_used: bool = False,
    provider_chain: str = "",
) -> None:
    """
    Persist LLM call metrics to DB and rolling window.
    Non-blocking — errors are swallowed to never affect the main request.
    """
    try:
        db = SessionLocal()
        log = LLMCallLog(
            provider           = response.provider.value,
            model              = response.model,
            task_type          = response.task_type.value,
            meeting_id         = meeting_id,
            user_id            = user_id,
            latency_ms         = response.latency_ms,
            prompt_tokens      = response.prompt_tokens,
            completion_tokens  = response.completion_tokens,
            total_tokens       = response.total_tokens,
            cost_usd           = response.cost_usd,
            quality_score      = response.quality_score,
            hallucination_risk = hallucination_risk,
            cache_hit          = response.cache_hit,
            success            = response.success,
            error_type         = type(response.error).__name__ if response.error else None,
            fallback_used      = fallback_used,
            provider_chain     = provider_chain[:200] if provider_chain else "",
        )
        db.add(log)
        db.commit()
        db.close()

        # Rolling window
        _add_to_rolling(response.provider.value, {
            "latency_ms":    response.latency_ms,
            "success":       response.success,
            "quality_score": response.quality_score or 0.0,
            "cost_usd":      response.cost_usd,
            "ts":            time.time(),
        })

    except Exception as exc:
        logger.warning(f"[Metrics] Failed to record call: {exc}")


# ── Aggregate stats ───────────────────────────────────────────────────────────

def get_provider_stats(db, hours: int = 24) -> list[dict]:
    """Aggregate stats per provider for the last N hours."""
    from sqlalchemy import text
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rows = db.execute(text("""
        SELECT
            provider,
            model,
            task_type,
            COUNT(*)                                          AS total_calls,
            COUNT(CASE WHEN success THEN 1 END)              AS success_count,
            COUNT(CASE WHEN NOT success THEN 1 END)          AS error_count,
            COUNT(CASE WHEN cache_hit THEN 1 END)            AS cache_hits,
            COUNT(CASE WHEN fallback_used THEN 1 END)        AS fallback_count,
            AVG(latency_ms)                                  AS avg_latency,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
            SUM(total_tokens)                                AS total_tokens,
            SUM(cost_usd)                                    AS total_cost,
            AVG(quality_score)                               AS avg_quality,
            AVG(hallucination_risk)                          AS avg_hallucination
        FROM llm_call_logs
        WHERE created_at >= :since
        GROUP BY provider, model, task_type
        ORDER BY total_calls DESC
    """), {"since": since}).fetchall()

    return [
        {
            "provider":          row.provider,
            "model":             row.model,
            "task_type":         row.task_type,
            "total_calls":       int(row.total_calls),
            "success_count":     int(row.success_count),
            "error_count":       int(row.error_count),
            "cache_hits":        int(row.cache_hits),
            "fallback_count":    int(row.fallback_count),
            "success_rate":      round(int(row.success_count) / int(row.total_calls) * 100, 1) if row.total_calls else 0,
            "avg_latency_ms":    round(float(row.avg_latency), 1) if row.avg_latency else 0,
            "p50_latency_ms":    round(float(row.p50_latency), 1) if row.p50_latency else 0,
            "p95_latency_ms":    round(float(row.p95_latency), 1) if row.p95_latency else 0,
            "total_tokens":      int(row.total_tokens or 0),
            "total_cost_usd":    round(float(row.total_cost or 0), 6),
            "avg_quality":       round(float(row.avg_quality), 3) if row.avg_quality else 0,
            "avg_hallucination": round(float(row.avg_hallucination), 3) if row.avg_hallucination else 0,
        }
        for row in rows
    ]


def get_rolling_stats() -> dict:
    """Real-time stats from in-memory rolling window."""
    result = {}
    for provider, entries in _rolling.items():
        if not entries:
            continue
        entries_list = list(entries)
        latencies = [e["latency_ms"] for e in entries_list]
        successes = [e for e in entries_list if e["success"]]
        result[provider] = {
            "recent_calls":   len(entries_list),
            "success_rate":   round(len(successes) / len(entries_list) * 100, 1),
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "avg_quality":    round(sum(e["quality_score"] for e in entries_list) / len(entries_list), 3),
            "total_cost_usd": round(sum(e["cost_usd"] for e in entries_list), 6),
        }
    return result


def get_quota_status() -> dict:
    """
    Estimate quota usage based on recent token counts.
    Gemini free tier: 1M tokens/day. OpenAI: based on billing.
    """
    from sqlalchemy import text
    from datetime import timedelta

    db = SessionLocal()
    try:
        since_1h  = datetime.now(timezone.utc) - timedelta(hours=1)
        since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

        rows = db.execute(text("""
            SELECT provider,
                   SUM(CASE WHEN created_at >= :since_1h  THEN total_tokens ELSE 0 END) AS tokens_1h,
                   SUM(CASE WHEN created_at >= :since_24h THEN total_tokens ELSE 0 END) AS tokens_24h,
                   SUM(CASE WHEN created_at >= :since_24h THEN cost_usd     ELSE 0 END) AS cost_24h
            FROM llm_call_logs
            WHERE created_at >= :since_24h
            GROUP BY provider
        """), {"since_1h": since_1h, "since_24h": since_24h}).fetchall()

        quota = {}
        LIMITS = {
            "gemini": {"daily_tokens": 1_000_000, "rpm": 60},
            "openai": {"daily_tokens": None,       "rpm": 500},
            "local":  {"daily_tokens": None,       "rpm": None},
        }
        for row in rows:
            lim = LIMITS.get(row.provider, {})
            daily_tokens = int(row.tokens_24h or 0)
            daily_limit  = lim.get("daily_tokens")
            quota[row.provider] = {
                "tokens_last_1h":  int(row.tokens_1h or 0),
                "tokens_last_24h": daily_tokens,
                "cost_last_24h":   round(float(row.cost_24h or 0), 4),
                "daily_limit":     daily_limit,
                "usage_pct":       round(daily_tokens / daily_limit * 100, 1) if daily_limit else None,
                "near_limit":      (daily_tokens / daily_limit > 0.8) if daily_limit else False,
            }
        return quota
    finally:
        db.close()

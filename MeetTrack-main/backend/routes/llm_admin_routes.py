"""
LLM Admin Routes — AI Provider Performance Dashboard
=====================================================

GET  /llm/status              — provider availability + circuit breakers
GET  /llm/metrics             — aggregate stats per provider/model/task
GET  /llm/metrics/rolling     — real-time rolling window stats
GET  /llm/metrics/quota       — quota usage per provider
GET  /llm/metrics/trend       — latency + cost trend over time
GET  /llm/metrics/quality     — quality score distribution
GET  /llm/logs                — paginated call log
POST /llm/test                — test a provider with a sample prompt
POST /llm/cache/clear         — clear response cache
GET  /llm/routing             — current routing table
PUT  /llm/routing             — override routing for a task type (runtime)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.services.llm.router import get_router, ROUTING_TABLE
from backend.services.llm.providers import ProviderName, TaskType
from backend.services.llm.metrics import (
    get_provider_stats, get_rolling_stats, get_quota_status, LLMCallLog,
)
from backend.services.llm.cache import cache_stats, _lru

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/llm", tags=["LLM Admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Provider status ───────────────────────────────────────────────────────────

@router.get("/status")
def get_llm_status(current_user=Depends(get_current_user)):
    """Provider availability, circuit breaker state, routing table."""
    llm_router = get_router()
    status = llm_router.status()
    status["cache"] = cache_stats()
    return status


# ── Aggregate metrics ─────────────────────────────────────────────────────────

@router.get("/metrics")
def get_metrics(
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate performance stats per provider/model/task type."""
    stats = get_provider_stats(db, hours=hours)
    rolling = get_rolling_stats()

    # Summary totals
    total_calls  = sum(s["total_calls"]  for s in stats)
    total_cost   = sum(s["total_cost_usd"] for s in stats)
    total_tokens = sum(s["total_tokens"] for s in stats)
    avg_quality  = (
        sum(s["avg_quality"] * s["total_calls"] for s in stats) / total_calls
        if total_calls else 0
    )

    return {
        "period_hours":  hours,
        "summary": {
            "total_calls":   total_calls,
            "total_cost_usd": round(total_cost, 6),
            "total_tokens":  total_tokens,
            "avg_quality":   round(avg_quality, 3),
        },
        "by_provider": stats,
        "rolling":     rolling,
    }


@router.get("/metrics/rolling")
def get_rolling_metrics(current_user=Depends(get_current_user)):
    """Real-time rolling window stats (last 1000 calls per provider)."""
    return get_rolling_stats()


@router.get("/metrics/quota")
def get_quota(current_user=Depends(get_current_user)):
    """Token quota usage per provider."""
    return get_quota_status()


@router.get("/metrics/trend")
def get_trend(
    hours: int = Query(24, ge=1, le=168),
    granularity: str = Query("hour", regex="^(hour|day)$"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latency and cost trend over time — for charts."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    trunc = "hour" if granularity == "hour" else "day"

    rows = db.execute(text(f"""
        SELECT
            DATE_TRUNC('{trunc}', created_at)  AS period,
            provider,
            COUNT(*)                            AS calls,
            AVG(latency_ms)                     AS avg_latency,
            SUM(cost_usd)                       AS total_cost,
            AVG(quality_score)                  AS avg_quality,
            COUNT(CASE WHEN NOT success THEN 1 END) AS errors
        FROM llm_call_logs
        WHERE created_at >= :since
        GROUP BY period, provider
        ORDER BY period ASC, provider
    """), {"since": since}).fetchall()

    return {
        "granularity": granularity,
        "data": [
            {
                "period":      row.period.isoformat() if row.period else "",
                "provider":    row.provider,
                "calls":       int(row.calls),
                "avg_latency": round(float(row.avg_latency), 1) if row.avg_latency else 0,
                "total_cost":  round(float(row.total_cost), 6) if row.total_cost else 0,
                "avg_quality": round(float(row.avg_quality), 3) if row.avg_quality else 0,
                "errors":      int(row.errors),
            }
            for row in rows
        ],
    }


@router.get("/metrics/quality")
def get_quality_distribution(
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quality score distribution and hallucination rates."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rows = db.execute(text("""
        SELECT
            provider,
            task_type,
            AVG(quality_score)       AS avg_quality,
            MIN(quality_score)       AS min_quality,
            MAX(quality_score)       AS max_quality,
            AVG(hallucination_risk)  AS avg_hallucination,
            COUNT(CASE WHEN hallucination_risk > 0.3 THEN 1 END) AS high_hallucination_count,
            COUNT(*)                 AS total
        FROM llm_call_logs
        WHERE created_at >= :since
          AND quality_score IS NOT NULL
        GROUP BY provider, task_type
        ORDER BY avg_quality DESC
    """), {"since": since}).fetchall()

    return {
        "data": [
            {
                "provider":                row.provider,
                "task_type":               row.task_type,
                "avg_quality":             round(float(row.avg_quality), 3) if row.avg_quality else 0,
                "min_quality":             round(float(row.min_quality), 3) if row.min_quality else 0,
                "max_quality":             round(float(row.max_quality), 3) if row.max_quality else 0,
                "avg_hallucination":       round(float(row.avg_hallucination), 3) if row.avg_hallucination else 0,
                "high_hallucination_count": int(row.high_hallucination_count),
                "total":                   int(row.total),
            }
            for row in rows
        ]
    }


# ── Call log ──────────────────────────────────────────────────────────────────

@router.get("/logs")
def get_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    success_only: bool = Query(False),
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated LLM call log with filters."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(LLMCallLog).filter(LLMCallLog.created_at >= since)

    if provider:
        q = q.filter(LLMCallLog.provider == provider)
    if task_type:
        q = q.filter(LLMCallLog.task_type == task_type)
    if success_only:
        q = q.filter(LLMCallLog.success == True)

    total = q.count()
    logs  = q.order_by(LLMCallLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "logs": [
            {
                "id":                 l.id,
                "provider":           l.provider,
                "model":              l.model,
                "task_type":          l.task_type,
                "meeting_id":         l.meeting_id,
                "latency_ms":         l.latency_ms,
                "total_tokens":       l.total_tokens,
                "cost_usd":           l.cost_usd,
                "quality_score":      l.quality_score,
                "hallucination_risk": l.hallucination_risk,
                "cache_hit":          l.cache_hit,
                "success":            l.success,
                "error_type":         l.error_type,
                "fallback_used":      l.fallback_used,
                "provider_chain":     l.provider_chain,
                "created_at":         l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


# ── Test endpoint ─────────────────────────────────────────────────────────────

class TestRequest(BaseModel):
    prompt: str
    task_type: str = "extraction"
    provider: Optional[str] = None  # force a specific provider


@router.post("/test")
def test_provider(
    req: TestRequest,
    current_user=Depends(get_current_user),
):
    """Test a provider with a custom prompt. Returns full response + metrics."""
    try:
        task_type = TaskType(req.task_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {req.task_type}")

    llm_router = get_router()

    if req.provider:
        # Force a specific provider
        try:
            pname = ProviderName(req.provider)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

        provider = llm_router._providers[pname]
        if not provider.is_available():
            raise HTTPException(status_code=400, detail=f"{req.provider} not available (no API key)")

        response = llm_router._call_with_timeout(provider, req.prompt, task_type, 1024, 30.0)
    else:
        response = llm_router.complete(
            prompt=req.prompt,
            task_type=task_type,
            use_cache=False,
        )

    return {
        "provider":      response.provider.value,
        "model":         response.model,
        "task_type":     response.task_type.value,
        "success":       response.success,
        "text":          response.text[:2000],
        "latency_ms":    response.latency_ms,
        "total_tokens":  response.total_tokens,
        "cost_usd":      response.cost_usd,
        "quality_score": response.quality_score,
        "error":         response.error,
        "cache_hit":     response.cache_hit,
    }


# ── Cache management ──────────────────────────────────────────────────────────

@router.post("/cache/clear")
def clear_cache(current_user=Depends(get_current_user)):
    """Clear the in-memory LRU cache."""
    _lru.clear()
    return {"cleared": True, "message": "In-memory cache cleared"}


@router.get("/cache/stats")
def get_cache_stats(current_user=Depends(get_current_user)):
    return cache_stats()


# ── Routing table ─────────────────────────────────────────────────────────────

@router.get("/routing")
def get_routing_table(current_user=Depends(get_current_user)):
    """Current task → provider routing table."""
    return {
        task.value: [p.value for p in providers]
        for task, providers in ROUTING_TABLE.items()
    }


class RoutingOverride(BaseModel):
    task_type: str
    providers: list[str]  # ordered preference list


@router.put("/routing")
def override_routing(
    override: RoutingOverride,
    current_user=Depends(get_current_user),
):
    """
    Override routing for a task type at runtime (no restart needed).
    Changes are in-memory only — reset on server restart.
    """
    try:
        task = TaskType(override.task_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_type: {override.task_type}")

    try:
        providers = [ProviderName(p) for p in override.providers]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {e}")

    ROUTING_TABLE[task] = providers
    logger.info(f"[LLM Admin] Routing override: {task.value} → {[p.value for p in providers]}")

    return {
        "task_type": task.value,
        "providers": [p.value for p in providers],
        "message":   "Routing updated (in-memory, resets on restart)",
    }

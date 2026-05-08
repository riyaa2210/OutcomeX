"""
Evaluation Routes
=================

Human feedback:
  POST /eval/feedback                  — submit thumbs up/down + corrections
  GET  /eval/feedback/{meeting_id}     — get feedback for a meeting

Evaluation results:
  GET  /eval/results/{meeting_id}      — get eval scores for a meeting
  POST /eval/run/{meeting_id}          — (re)run evaluation for a meeting
  GET  /eval/results                   — paginated eval results list

Benchmark:
  GET  /eval/benchmark                 — list benchmark samples
  POST /eval/benchmark                 — create benchmark sample
  POST /eval/benchmark/run             — run benchmark suite
  DELETE /eval/benchmark/{id}          — delete a sample

Reports:
  GET  /eval/report                    — automated evaluation report
  GET  /eval/report/download           — download report as JSON

Monitoring:
  GET  /eval/dashboard                 — overview metrics for monitoring dashboard
  GET  /eval/refinements               — prompt refinement suggestions
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.evaluation import EvalResult, HumanFeedback, BenchmarkSample, FeedbackSignal
from backend.models.meeting import Meeting
from backend.services.evaluation_service import (
    evaluate_meeting_output,
    process_human_feedback,
    run_benchmark,
    generate_eval_report,
    get_refinement_suggestions,
    compute_precision_recall,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eval", tags=["Evaluation"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Human feedback ────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    meeting_id:          int
    signal:              str                    # thumbs_up / thumbs_down / edited / flagged
    dimension:           Optional[str] = None
    original_summary:    Optional[str] = None
    original_decisions:  Optional[list] = None
    original_actions:    Optional[list] = None
    corrected_summary:   Optional[str] = None
    corrected_decisions: Optional[list] = None
    corrected_actions:   Optional[list] = None
    confidence_votes:    Optional[dict] = None  # {item_index: true/false}
    comment:             Optional[str] = None


@router.post("/feedback")
def submit_feedback(
    req: FeedbackRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit human feedback (thumbs up/down, corrections, confidence votes)."""
    try:
        signal = FeedbackSignal(req.signal)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid signal: {req.signal}")

    # Verify meeting belongs to user
    meeting = db.query(Meeting).filter(
        Meeting.id == req.meeting_id,
        Meeting.user_id == current_user.id,
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    feedback = HumanFeedback(
        meeting_id          = req.meeting_id,
        user_id             = current_user.id,
        signal              = signal,
        dimension           = req.dimension,
        original_summary    = req.original_summary,
        original_decisions  = req.original_decisions,
        original_actions    = req.original_actions,
        corrected_summary   = req.corrected_summary,
        corrected_decisions = req.corrected_decisions,
        corrected_actions   = req.corrected_actions,
        confidence_votes    = req.confidence_votes,
        comment             = req.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # Process diff + update eval result
    diff_result = process_human_feedback(db, feedback)

    return {
        "feedback_id": feedback.id,
        "signal":      signal.value,
        "diff":        diff_result["diff"],
        "precision_recall": diff_result["precision_recall"],
        "message":     "Feedback recorded. Thank you!",
    }


@router.get("/feedback/{meeting_id}")
def get_feedback(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all feedback for a meeting."""
    feedbacks = db.query(HumanFeedback).filter(
        HumanFeedback.meeting_id == meeting_id,
        HumanFeedback.user_id == current_user.id,
    ).order_by(HumanFeedback.created_at.desc()).all()

    return {
        "meeting_id": meeting_id,
        "count":      len(feedbacks),
        "feedback": [
            {
                "id":               f.id,
                "signal":           f.signal.value,
                "dimension":        f.dimension,
                "actions_added":    f.actions_added,
                "actions_removed":  f.actions_removed,
                "actions_edited":   f.actions_edited,
                "summary_edited":   f.summary_edited,
                "comment":          f.comment,
                "created_at":       f.created_at.isoformat() if f.created_at else None,
            }
            for f in feedbacks
        ],
    }


# ── Evaluation results ────────────────────────────────────────────────────────

@router.get("/results/{meeting_id}")
def get_eval_result(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get evaluation scores for a specific meeting."""
    ev = db.query(EvalResult).filter(EvalResult.meeting_id == meeting_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="No evaluation found for this meeting")

    return _serialize_eval(ev)


@router.post("/run/{meeting_id}")
def run_evaluation(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """(Re)run automated evaluation for a meeting."""
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id,
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="Meeting has no transcript")

    # Get latest AI output from result table
    from backend.models.result import Result
    result = db.query(Result).filter(Result.meeting_id == meeting_id).first()

    summary   = ""
    decisions = []
    actions   = []

    if result and result.summary:
        try:
            parsed    = json.loads(result.summary)
            summary   = parsed.get("summary", "")
            decisions = parsed.get("decisions", [])
            actions   = parsed.get("action_items", [])
        except Exception:
            summary = result.summary or ""

    # Also pull action items from DB
    from backend.models.action_item import ActionItem
    db_actions = db.query(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()
    if db_actions and not actions:
        actions = [
            {
                "task":             a.description or a.title or "",
                "assignee":         a.assigned_to or "Unassigned",
                "deadline":         a.deadline,
                "confidence_score": 0.8,
            }
            for a in db_actions
        ]

    ev = evaluate_meeting_output(
        db=db,
        meeting_id=meeting_id,
        transcript=meeting.transcript,
        summary=summary,
        decisions=decisions,
        action_items=actions,
        user_id=current_user.id,
    )

    return _serialize_eval(ev)


@router.get("/results")
def list_eval_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    min_score: Optional[float] = Query(None),
    max_hallucination: Optional[float] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated list of evaluation results."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = db.query(EvalResult).filter(EvalResult.created_at >= since)
    if current_user.id:
        q = q.filter(EvalResult.user_id == current_user.id)
    if min_score is not None:
        q = q.filter(EvalResult.overall_score >= min_score)
    if max_hallucination is not None:
        q = q.filter(EvalResult.hallucination_score <= max_hallucination)

    total = q.count()
    rows  = q.order_by(EvalResult.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "results":   [_serialize_eval(ev) for ev in rows],
    }


def _serialize_eval(ev: EvalResult) -> dict:
    return {
        "id":                      ev.id,
        "meeting_id":              ev.meeting_id,
        "provider":                ev.provider,
        "model":                   ev.model,
        "overall_score":           ev.overall_score,
        "summary_quality_score":   ev.summary_quality_score,
        "decision_accuracy_score": ev.decision_accuracy_score,
        "action_precision_score":  ev.action_precision_score,
        "hallucination_score":     ev.hallucination_score,
        "groundedness_score":      ev.groundedness_score,
        "completeness_score":      ev.completeness_score,
        "precision":               ev.precision,
        "recall":                  ev.recall,
        "f1_score":                ev.f1_score,
        "flagged_terms":           ev.flagged_terms or [],
        "unsupported_claims":      ev.unsupported_claims or [],
        "fabricated_deadlines":    ev.fabricated_deadlines or [],
        "incorrect_assignees":     ev.incorrect_assignees or [],
        "action_items_count":      ev.action_items_count,
        "decisions_count":         ev.decisions_count,
        "low_confidence_items":    ev.low_confidence_items,
        "prompt_version":          ev.prompt_version,
        "created_at":              ev.created_at.isoformat() if ev.created_at else None,
    }


# ── Benchmark ─────────────────────────────────────────────────────────────────

class BenchmarkCreateRequest(BaseModel):
    transcript_excerpt:  str
    expected_summary:    Optional[str] = None
    expected_decisions:  Optional[list] = None
    expected_actions:    Optional[list] = None
    category:            str = "general"
    difficulty:          str = "medium"
    notes:               Optional[str] = None
    meeting_id:          Optional[int] = None


@router.get("/benchmark")
def list_benchmarks(
    category: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all benchmark samples."""
    q = db.query(BenchmarkSample)
    if category:
        q = q.filter(BenchmarkSample.category == category)
    samples = q.order_by(BenchmarkSample.created_at.desc()).limit(100).all()

    return {
        "count": len(samples),
        "samples": [
            {
                "id":               s.id,
                "category":         s.category,
                "difficulty":       s.difficulty,
                "excerpt_preview":  s.transcript_excerpt[:100] + "…",
                "expected_actions": len(s.expected_actions or []),
                "last_run_at":      s.last_run_at.isoformat() if s.last_run_at else None,
                "last_run_scores":  s.last_run_scores,
                "best_provider":    s.best_provider,
                "created_at":       s.created_at.isoformat() if s.created_at else None,
            }
            for s in samples
        ],
    }


@router.post("/benchmark")
def create_benchmark(
    req: BenchmarkCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new benchmark sample from a transcript excerpt."""
    if len(req.transcript_excerpt) < 50:
        raise HTTPException(status_code=400, detail="Transcript excerpt too short (min 50 chars)")

    sample = BenchmarkSample(
        transcript_excerpt = req.transcript_excerpt[:2000],
        expected_summary   = req.expected_summary,
        expected_decisions = req.expected_decisions or [],
        expected_actions   = req.expected_actions or [],
        category           = req.category,
        difficulty         = req.difficulty,
        notes              = req.notes,
        meeting_id         = req.meeting_id,
        created_by         = current_user.id,
        source             = "human_correction",
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)

    return {"id": sample.id, "message": "Benchmark sample created"}


@router.post("/benchmark/run")
def run_benchmark_suite(
    sample_ids: Optional[list[int]] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the benchmark suite and return leaderboard."""
    result = run_benchmark(db, sample_ids=sample_ids)
    return result


@router.delete("/benchmark/{sample_id}")
def delete_benchmark(
    sample_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sample = db.query(BenchmarkSample).filter(BenchmarkSample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    db.delete(sample)
    db.commit()
    return {"deleted": True}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/report")
def get_report(
    days: int = Query(7, ge=1, le=90),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate automated evaluation report."""
    return generate_eval_report(db, days=days)


@router.get("/report/download")
def download_report(
    days: int = Query(7, ge=1, le=90),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download evaluation report as JSON."""
    report = generate_eval_report(db, days=days)
    import io
    content = json.dumps(report, indent=2)
    return StreamingResponse(
        io.StringIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=eval_report_{days}d.json"},
    )


# ── Monitoring dashboard ──────────────────────────────────────────────────────

@router.get("/dashboard")
def get_eval_dashboard(
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Monitoring dashboard: model accuracy, token usage, latency, failure rates.
    Combines eval results + LLM call logs.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Eval summary
    eval_stats = db.execute(text("""
        SELECT
            COUNT(*)                         AS total,
            AVG(overall_score)               AS avg_overall,
            AVG(hallucination_score)         AS avg_hallucination,
            AVG(action_precision_score)      AS avg_precision,
            AVG(f1_score)                    AS avg_f1,
            COUNT(CASE WHEN overall_score < 0.5 THEN 1 END) AS low_quality_count,
            COUNT(CASE WHEN hallucination_score > 0.3 THEN 1 END) AS high_hallucination_count
        FROM eval_results
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    # LLM performance
    llm_stats = db.execute(text("""
        SELECT
            COUNT(*)                                    AS total_calls,
            AVG(latency_ms)                             AS avg_latency,
            SUM(total_tokens)                           AS total_tokens,
            SUM(cost_usd)                               AS total_cost,
            COUNT(CASE WHEN NOT success THEN 1 END)     AS failures,
            COUNT(CASE WHEN fallback_used THEN 1 END)   AS fallbacks,
            COUNT(CASE WHEN cache_hit THEN 1 END)       AS cache_hits
        FROM llm_call_logs
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    # Human feedback summary
    fb_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN signal = 'thumbs_up'   THEN 1 END) AS thumbs_up,
            COUNT(CASE WHEN signal = 'thumbs_down' THEN 1 END) AS thumbs_down,
            COUNT(CASE WHEN signal = 'edited'      THEN 1 END) AS edited,
            COUNT(CASE WHEN signal = 'flagged'     THEN 1 END) AS flagged,
            COUNT(*)                                            AS total
        FROM human_feedback
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    # Score trend (hourly)
    trend = db.execute(text("""
        SELECT
            DATE_TRUNC('hour', created_at) AS hour,
            AVG(overall_score)             AS avg_score,
            AVG(hallucination_score)       AS avg_hallucination,
            COUNT(*)                       AS evals
        FROM eval_results
        WHERE created_at >= :since
        GROUP BY hour
        ORDER BY hour ASC
    """), {"since": since}).fetchall()

    def _f(v): return round(float(v), 3) if v is not None else 0.0
    def _i(v): return int(v) if v is not None else 0

    total_calls = _i(llm_stats.total_calls)
    failures    = _i(llm_stats.failures)

    return {
        "period_hours": hours,
        "model_accuracy": {
            "total_evaluations":       _i(eval_stats.total),
            "avg_overall_score":       _f(eval_stats.avg_overall),
            "avg_hallucination":       _f(eval_stats.avg_hallucination),
            "avg_action_precision":    _f(eval_stats.avg_precision),
            "avg_f1_score":            _f(eval_stats.avg_f1),
            "low_quality_count":       _i(eval_stats.low_quality_count),
            "high_hallucination_count": _i(eval_stats.high_hallucination_count),
        },
        "llm_performance": {
            "total_calls":    total_calls,
            "avg_latency_ms": _f(llm_stats.avg_latency),
            "total_tokens":   _i(llm_stats.total_tokens),
            "total_cost_usd": _f(llm_stats.total_cost),
            "failure_count":  failures,
            "failure_rate":   round(failures / total_calls * 100, 1) if total_calls else 0,
            "fallback_count": _i(llm_stats.fallbacks),
            "cache_hits":     _i(llm_stats.cache_hits),
            "cache_hit_rate": round(_i(llm_stats.cache_hits) / total_calls * 100, 1) if total_calls else 0,
        },
        "human_feedback": {
            "total":       _i(fb_stats.total),
            "thumbs_up":   _i(fb_stats.thumbs_up),
            "thumbs_down": _i(fb_stats.thumbs_down),
            "edited":      _i(fb_stats.edited),
            "flagged":     _i(fb_stats.flagged),
            "satisfaction_rate": round(
                _i(fb_stats.thumbs_up) / max(_i(fb_stats.total), 1) * 100, 1
            ),
        },
        "score_trend": [
            {
                "hour":             row.hour.isoformat() if row.hour else "",
                "avg_score":        _f(row.avg_score),
                "avg_hallucination": _f(row.avg_hallucination),
                "evals":            _i(row.evals),
            }
            for row in trend
        ],
    }


@router.get("/refinements")
def get_refinements(
    days: int = Query(7, ge=1, le=30),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get prompt refinement suggestions based on recent failure patterns."""
    return {"suggestions": get_refinement_suggestions(db, days=days)}

"""
Analytics Routes — Enterprise Dashboard APIs
=============================================

GET /analytics/overview          — key metrics summary
GET /analytics/meetings-trend    — meetings per day/week/month
GET /analytics/action-items      — completion rate, overdue, by assignee
GET /analytics/decisions         — decision-to-action ratio
GET /analytics/productivity      — team productivity trends
GET /analytics/ai-insights       — AI-powered efficiency + sentiment
GET /analytics/heatmap           — meeting activity heatmap (day × hour)
GET /analytics/report            — downloadable CSV/JSON report

All endpoints support query params:
  ?days=30          — lookback window (default 30)
  ?assignee=Alice   — filter by person
  ?department=Eng   — filter by department (from user profile)
"""

import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.meeting import Meeting
from backend.models.action_item import ActionItem
from backend.models.result import Result
from backend.services.analytics_service import (
    compute_ai_insights,
    compute_efficiency_score,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# ── Overview ──────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Key metrics summary card data."""
    since = _since(days)
    uid   = current_user.id

    total_meetings = db.query(func.count(Meeting.id)).filter(
        Meeting.user_id == uid,
        Meeting.created_at >= since,
    ).scalar() or 0

    total_actions = db.query(func.count(ActionItem.id)).join(
        Meeting, ActionItem.meeting_id == Meeting.id
    ).filter(
        Meeting.user_id == uid,
        Meeting.created_at >= since,
    ).scalar() or 0

    completed_actions = db.query(func.count(ActionItem.id)).join(
        Meeting, ActionItem.meeting_id == Meeting.id
    ).filter(
        Meeting.user_id == uid,
        Meeting.created_at >= since,
        ActionItem.status.in_(["Completed", "Done", "done", "completed"]),
    ).scalar() or 0

    overdue_actions = db.query(func.count(ActionItem.id)).join(
        Meeting, ActionItem.meeting_id == Meeting.id
    ).filter(
        Meeting.user_id == uid,
        ActionItem.deadline.isnot(None),
        ActionItem.status.notin_(["Completed", "Done", "done", "completed"]),
    ).scalar() or 0

    completion_rate = round(completed_actions / total_actions * 100, 1) if total_actions else 0.0

    # Decision count from results JSON
    decisions_total = _count_decisions(db, uid, since)

    decision_to_action = round(decisions_total / total_actions, 2) if total_actions else 0.0

    return {
        "period_days":        days,
        "total_meetings":     total_meetings,
        "total_actions":      total_actions,
        "completed_actions":  completed_actions,
        "overdue_actions":    overdue_actions,
        "completion_rate":    completion_rate,
        "decisions_total":    decisions_total,
        "decision_to_action": decision_to_action,
        "meetings_per_week":  round(total_meetings / max(days / 7, 1), 1),
    }


def _count_decisions(db, user_id, since) -> int:
    results = db.query(Result.summary).join(
        Meeting, Result.meeting_id == Meeting.id
    ).filter(
        Meeting.user_id == user_id,
        Meeting.created_at >= since,
        Result.summary.isnot(None),
    ).all()

    count = 0
    for (summary,) in results:
        try:
            parsed = json.loads(summary)
            count += len(parsed.get("decisions", []))
        except Exception:
            pass
    return count


# ── Meetings trend ────────────────────────────────────────────────────────────

@router.get("/meetings-trend")
def get_meetings_trend(
    days: int = Query(30, ge=7, le=365),
    granularity: str = Query("day", regex="^(day|week|month)$"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Meetings per day/week/month for area chart."""
    since = _since(days)
    uid   = current_user.id

    if granularity == "day":
        trunc = "day"
    elif granularity == "week":
        trunc = "week"
    else:
        trunc = "month"

    rows = db.execute(text("""
        SELECT
            DATE_TRUNC(:trunc, created_at) AS period,
            COUNT(*) AS meeting_count
        FROM meetings
        WHERE user_id = :uid
          AND created_at >= :since
        GROUP BY period
        ORDER BY period ASC
    """), {"trunc": trunc, "uid": uid, "since": since}).fetchall()

    return {
        "granularity": granularity,
        "data": [
            {
                "date":  row.period.strftime("%Y-%m-%d") if row.period else "",
                "count": int(row.meeting_count),
            }
            for row in rows
        ],
    }


# ── Action items analytics ────────────────────────────────────────────────────

@router.get("/action-items")
def get_action_analytics(
    days: int = Query(30, ge=1, le=365),
    assignee: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Action item completion by assignee + status breakdown."""
    since = _since(days)
    uid   = current_user.id

    q = db.query(
        ActionItem.assigned_to,
        ActionItem.status,
        func.count(ActionItem.id).label("cnt"),
    ).join(Meeting, ActionItem.meeting_id == Meeting.id).filter(
        Meeting.user_id == uid,
        Meeting.created_at >= since,
    )

    if assignee:
        q = q.filter(ActionItem.assigned_to.ilike(f"%{assignee}%"))

    rows = q.group_by(ActionItem.assigned_to, ActionItem.status).all()

    # Aggregate by assignee
    by_assignee: dict = {}
    for row in rows:
        name = row.assigned_to or "Unassigned"
        if name not in by_assignee:
            by_assignee[name] = {"name": name, "total": 0, "completed": 0, "pending": 0, "overdue": 0}
        by_assignee[name]["total"] += row.cnt
        status_lower = (row.status or "").lower()
        if status_lower in ("completed", "done"):
            by_assignee[name]["completed"] += row.cnt
        elif status_lower == "overdue":
            by_assignee[name]["overdue"] += row.cnt
        else:
            by_assignee[name]["pending"] += row.cnt

    result = list(by_assignee.values())
    for r in result:
        r["completion_rate"] = round(r["completed"] / r["total"] * 100, 1) if r["total"] else 0.0

    result.sort(key=lambda x: x["total"], reverse=True)
    return {"data": result[:20]}  # top 20 assignees


# ── Productivity trend ────────────────────────────────────────────────────────

@router.get("/productivity")
def get_productivity_trend(
    days: int = Query(60, ge=14, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Weekly productivity: meetings + completion rate trend."""
    since = _since(days)
    uid   = current_user.id

    rows = db.execute(text("""
        SELECT
            DATE_TRUNC('week', m.created_at) AS week,
            COUNT(DISTINCT m.id) AS meetings,
            COUNT(ai.id) AS total_actions,
            COUNT(CASE WHEN LOWER(ai.status) IN ('completed','done') THEN 1 END) AS done_actions
        FROM meetings m
        LEFT JOIN action_items ai ON ai.meeting_id = m.id
        WHERE m.user_id = :uid
          AND m.created_at >= :since
        GROUP BY week
        ORDER BY week ASC
    """), {"uid": uid, "since": since}).fetchall()

    return {
        "data": [
            {
                "week":            row.week.strftime("%Y-%m-%d") if row.week else "",
                "meetings":        int(row.meetings),
                "total_actions":   int(row.total_actions),
                "done_actions":    int(row.done_actions),
                "completion_rate": round(
                    int(row.done_actions) / int(row.total_actions) * 100, 1
                ) if row.total_actions else 0.0,
            }
            for row in rows
        ]
    }


# ── Heatmap ───────────────────────────────────────────────────────────────────

@router.get("/heatmap")
def get_heatmap(
    days: int = Query(90, ge=7, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Meeting activity heatmap: day-of-week × hour-of-day."""
    since = _since(days)
    uid   = current_user.id

    rows = db.execute(text("""
        SELECT
            EXTRACT(DOW FROM created_at)  AS dow,
            EXTRACT(HOUR FROM created_at) AS hour,
            COUNT(*) AS cnt
        FROM meetings
        WHERE user_id = :uid
          AND created_at >= :since
        GROUP BY dow, hour
        ORDER BY dow, hour
    """), {"uid": uid, "since": since}).fetchall()

    DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    data = [
        {
            "day":   DAYS[int(row.dow)],
            "hour":  int(row.hour),
            "value": int(row.cnt),
        }
        for row in rows
    ]
    return {"data": data}


# ── AI insights ───────────────────────────────────────────────────────────────

@router.get("/ai-insights")
async def get_ai_insights(
    days: int = Query(30, ge=7, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-powered insights: efficiency score, sentiment, blockers, imbalance."""
    since = _since(days)
    insights = await compute_ai_insights(db, current_user.id, since)
    return insights


# ── Downloadable report ───────────────────────────────────────────────────────

@router.get("/report")
def download_report(
    days: int = Query(30, ge=1, le=365),
    fmt: str = Query("csv", regex="^(csv|json)$"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download meetings + action items as CSV or JSON."""
    since = _since(days)
    uid   = current_user.id

    rows = db.execute(text("""
        SELECT
            m.id          AS meeting_id,
            m.title       AS meeting_title,
            m.created_at  AS meeting_date,
            ai.description AS task,
            ai.assigned_to,
            ai.deadline,
            ai.status
        FROM meetings m
        LEFT JOIN action_items ai ON ai.meeting_id = m.id
        WHERE m.user_id = :uid
          AND m.created_at >= :since
        ORDER BY m.created_at DESC, ai.id
    """), {"uid": uid, "since": since}).fetchall()

    if fmt == "json":
        data = [
            {
                "meeting_id":    row.meeting_id,
                "meeting_title": row.meeting_title,
                "meeting_date":  row.meeting_date.isoformat() if row.meeting_date else "",
                "task":          row.task or "",
                "assigned_to":   row.assigned_to or "",
                "deadline":      row.deadline or "",
                "status":        row.status or "",
            }
            for row in rows
        ]
        return StreamingResponse(
            io.StringIO(json.dumps(data, indent=2)),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=outcomex_report_{days}d.json"},
        )

    # CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Meeting ID", "Title", "Date", "Task", "Assigned To", "Deadline", "Status"])
    for row in rows:
        writer.writerow([
            row.meeting_id,
            row.meeting_title or "",
            row.meeting_date.strftime("%Y-%m-%d %H:%M") if row.meeting_date else "",
            row.task or "",
            row.assigned_to or "",
            row.deadline or "",
            row.status or "",
        ])
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=outcomex_report_{days}d.csv"},
    )

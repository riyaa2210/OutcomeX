"""
RAG Routes — Ask Meetings + Semantic Search
===========================================

POST /ask-meetings          — natural language query over all meetings
GET  /semantic-search       — keyword + vector search
GET  /rag/query-history     — past queries and answers
POST /rag/index/{meeting_id} — manually re-index a meeting
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.services.rag_service import ask_meetings, similarity_search, index_meeting
from backend.models.meeting_chunk import QueryHistory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG / Ask Meetings"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Request / Response schemas ────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str
    meeting_id: Optional[int] = None   # scope to a specific meeting


class AskResponse(BaseModel):
    answer:      str
    sources:     list
    confidence:  float
    chunks_used: int


# ── POST /ask-meetings ────────────────────────────────────────────────────────

@router.post("/ask-meetings", response_model=AskResponse)
async def ask_meetings_endpoint(
    request: AskRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Natural language query over all your meetings.

    Examples:
      "What tasks were assigned to Alice?"
      "Which meetings discussed JWT authentication?"
      "What decisions were made about the deployment?"
      "Summarise all action items from last week"
    """
    if not request.query or len(request.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short")

    if len(request.query) > 500:
        raise HTTPException(status_code=400, detail="Query too long (max 500 chars)")

    result = ask_meetings(
        db         = db,
        query      = request.query.strip(),
        user_id    = current_user.id,
        meeting_id = request.meeting_id,
    )

    return AskResponse(**result)


# ── GET /semantic-search ──────────────────────────────────────────────────────

@router.get("/semantic-search")
async def semantic_search(
    q: str = Query(..., description="Search query"),
    meeting_id: Optional[int] = Query(None, description="Filter by meeting"),
    chunk_type: Optional[str] = Query(None, description="transcript|summary|decision"),
    top_k: int = Query(5, ge=1, le=20),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Semantic search across all meeting chunks.
    Returns ranked chunks with similarity scores.
    """
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query too short")

    chunks = similarity_search(
        db         = db,
        query      = q.strip(),
        user_id    = current_user.id,
        meeting_id = meeting_id,
        chunk_type = chunk_type,
        top_k      = top_k,
    )

    return {
        "query":   q,
        "results": chunks,
        "count":   len(chunks),
    }


# ── GET /rag/query-history ────────────────────────────────────────────────────

@router.get("/query-history")
async def get_query_history(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the user's past queries and AI answers."""
    records = (
        db.query(QueryHistory)
        .filter(QueryHistory.user_id == current_user.id)
        .order_by(QueryHistory.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id":         r.id,
            "query":      r.query,
            "answer":     r.answer,
            "confidence": r.confidence,
            "sources":    r.sources or [],
            "created_at": r.created_at,
        }
        for r in records
    ]


# ── POST /rag/index/{meeting_id} ──────────────────────────────────────────────

@router.post("/index/{meeting_id}")
async def index_meeting_endpoint(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually re-index a meeting's transcript for RAG search.
    Useful after editing a transcript or if indexing failed.
    """
    from backend.models.meeting import Meeting
    from backend.models.result import Result

    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id,
    ).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.transcript:
        raise HTTPException(status_code=400, detail="Meeting has no transcript to index")

    # Get summary + decisions if available
    result = db.query(Result).filter(Result.meeting_id == meeting_id).first()
    summary   = ""
    decisions = []
    if result and result.summary:
        import json
        try:
            parsed = json.loads(result.summary)
            summary   = parsed.get("summary", "")
            decisions = parsed.get("decisions", [])
        except Exception:
            summary = result.summary

    chunks_stored = index_meeting(
        db         = db,
        meeting_id = meeting_id,
        user_id    = current_user.id,
        transcript = meeting.transcript,
        title      = meeting.title or f"Meeting #{meeting_id}",
        summary    = summary,
        decisions  = decisions,
    )

    return {
        "status":        "indexed",
        "meeting_id":    meeting_id,
        "chunks_stored": chunks_stored,
    }

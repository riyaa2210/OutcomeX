from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.meeting import Meeting
from backend.models.result import Result

router = APIRouter(prefix="/meetings", tags=["Meetings"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Create blank meeting (used by Live Meeting page) ──────────────────────────

class CreateMeetingRequest(BaseModel):
    title: Optional[str] = "Untitled Meeting"


@router.post("/create")
def create_blank_meeting(
    req: CreateMeetingRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a blank meeting — used by the Live Meeting page to get a real ID."""
    meeting = Meeting(
        user_id    = current_user.id,
        title      = req.title or "Live Meeting",
        transcript = "",
        created_at = datetime.utcnow(),
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return {"id": meeting.id, "title": meeting.title, "created_at": meeting.created_at}


# ── List meetings ─────────────────────────────────────────────────────────────

@router.get("/")
def list_meetings(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meetings = db.query(Meeting).filter(Meeting.user_id == current_user.id).all()
    return [
        {
            "id":         m.id,
            "title":      m.title,
            "audio_path": m.audio_path,
            "created_at": m.created_at,
            "user_id":    m.user_id,
        }
        for m in meetings
    ]


# ── Get single meeting ────────────────────────────────────────────────────────

@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id,
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {
        "id":         meeting.id,
        "title":      meeting.title,
        "transcript": meeting.transcript,
        "audio_path": meeting.audio_path,
        "created_at": meeting.created_at,
        "user_id":    meeting.user_id,
    }


@router.get("/{meeting_id}/transcript")
def get_transcript(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id,
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"meeting_id": meeting.id, "title": meeting.title, "transcript": meeting.transcript}


@router.get("/{meeting_id}/summary")
def get_summary(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = db.query(Result).filter(Result.meeting_id == meeting_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Summary not found")
    return {
        "meeting_id": meeting_id,
        "summary":    result.summary,
        "created_at": result.created_at,
    }

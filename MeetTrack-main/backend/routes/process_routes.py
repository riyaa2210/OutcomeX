"""
Process Routes

POST /                          — process a meeting from a file path (legacy)
POST /generate-summary/{id}     — (re)generate structured summary for a meeting
POST /approve-summary           — approve or reject a summary
"""

import os
import json
import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from backend.models.result import Result
from backend.models.meeting import Meeting
from backend.models.action_item import ActionItem
from backend.schemas.result_schema import SummaryApproval
from backend.services.transcribe_service import transcribe_audio
from backend.services.nlp_service import extract_action_items
from backend.services.summary_service import generate_summary, generate_structured_summary
from backend.services.n8n_service import trigger_n8n_workflow
from backend.app.database import SessionLocal
from backend.app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Legacy process endpoint
# ---------------------------------------------------------------------------

@router.post("/")
def process_meeting(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        transcript = transcribe_audio(file_path)
        logger.info("[Process] Transcript generated")

        new_meeting = Meeting(
            user_id=current_user.id,
            title="Untitled Meeting",
            audio_path=file_path,
            transcript=transcript,
        )
        db.add(new_meeting)
        db.commit()
        db.refresh(new_meeting)

        # Use new structured pipeline
        structured = generate_structured_summary(transcript)
        action_items_out = []

        for item in structured.get("action_items", []):
            if item.get("confidence_score", 1.0) < 0.4:
                continue
            action = ActionItem(
                meeting_id=new_meeting.id,
                assigned_to=item.get("assignee") or "Unassigned",
                title=item.get("task", "")[:100],
                description=item.get("task", ""),
                deadline=item.get("deadline"),
                status="Pending",
            )
            db.add(action)
            action_items_out.append(item)

        db.commit()

        background_tasks.add_task(
            trigger_n8n_workflow,
            db,
            new_meeting.id,
            transcript,
            structured,
            "meeting_processed",
        )

        return {
            "status": "success",
            "meeting_id": new_meeting.id,
            "transcript": transcript,
            "structured_output": structured,
            # legacy key
            "action_items": action_items_out,
        }

    except Exception as exc:
        logger.error(f"[Process] ERROR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Generate / regenerate structured summary
# ---------------------------------------------------------------------------

@router.post("/generate-summary/{meeting_id}")
def generate_summary_api(
    meeting_id: int,
    db: Session = Depends(get_db),
):
    """
    (Re)generate a structured summary for a meeting.
    Returns the full structured output:
      { summary, decisions, action_items }
    Also persists the JSON to Result.summary.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    transcript = meeting.transcript
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript missing for this meeting")

    # Get or create Result row
    result = db.query(Result).filter(Result.meeting_id == meeting_id).first()
    if not result:
        result = Result(meeting_id=meeting_id, transcript=transcript)
        db.add(result)
        db.commit()
        db.refresh(result)

    # Run structured pipeline
    structured = generate_structured_summary(transcript)

    # Persist as JSON string
    result.summary = json.dumps(structured, indent=2)
    db.commit()

    return {
        "meeting_id": meeting_id,
        "structured_output": structured,
        # legacy field for any frontend that reads .summary as plain text
        "summary": structured.get("summary", ""),
    }


# ---------------------------------------------------------------------------
# Approve / reject summary
# ---------------------------------------------------------------------------

@router.post("/approve-summary")
def approve_summary(data: SummaryApproval, db: Session = Depends(get_db)):
    result = db.query(Result).filter(Result.meeting_id == data.meeting_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Meeting not found")

    result.summary_approved = data.approved
    if not data.approved:
        result.summary = None

    db.commit()
    return {"message": "Summary updated", "approved": data.approved}

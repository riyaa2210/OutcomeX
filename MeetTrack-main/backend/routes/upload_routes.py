"""
Upload & Processing Routes

POST /audio   — save uploaded audio file
POST /process — full pipeline: transcribe → NLP pre-process → LLM extraction → persist
"""

import os
import json
import shutil
import logging
import traceback
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.models.meeting import Meeting
from backend.models.action_item import ActionItem
from backend.services.transcribe_service import transcribe_audio
from backend.services.summary_service import generate_structured_summary
from backend.services.n8n_service import trigger_n8n_workflow

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ProcessRequest(BaseModel):
    file_path: str
    file_name: str = "Unknown"


class TranscriptProcessRequest(BaseModel):
    """Process a meeting from a raw transcript string — no audio needed."""
    transcript: str
    title: str = "Untitled Meeting"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Upload audio file
# ---------------------------------------------------------------------------

@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, file.filename))
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "message": "Upload successful",
            "file_path": file_path,
            "file_name": file.filename,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


# ---------------------------------------------------------------------------
# Process meeting — full pipeline
# ---------------------------------------------------------------------------

@router.post("/process")
async def process_meeting(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full meeting processing pipeline:
      1. Transcribe audio (Whisper)
      2. Pre-process transcript (clean, detect speakers, extract key sentences)
      3. LLM structured extraction (summary + decisions + action items)
      4. Persist meeting + action items
      5. Return structured JSON response
    """
    try:
        logger.info(f"[Process] Starting for user {current_user.id}")
        file_path = request.file_path
        file_name = request.file_name

        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail="File not found")

        # ------------------------------------------------------------------
        # Step 1 — Transcribe via Colab Whisper API
        # ------------------------------------------------------------------
        logger.info("[Process] Step 1: Sending audio to Colab Whisper API…")
        try:
            transcript = transcribe_audio(file_path)
            logger.info(f"[Process] Transcription received: {len(transcript)} chars")
        except (RuntimeError, FileNotFoundError) as exc:
            logger.error(f"[Process] Transcription failed: {exc}")
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        # ------------------------------------------------------------------
        # Step 2 — Create meeting record
        # ------------------------------------------------------------------
        logger.info("[Process] Step 2: Creating meeting record…")
        title = (
            file_name
            .replace(".mp3", "")
            .replace(".wav", "")
            .replace(".m4a", "")
            .replace(".ogg", "")
            .strip() or "Untitled Meeting"
        )
        new_meeting = Meeting(
            user_id=current_user.id,
            title=title,
            audio_path=file_path,
            transcript=transcript,
            created_at=datetime.utcnow(),
        )
        db.add(new_meeting)
        db.commit()
        db.refresh(new_meeting)
        logger.info(f"[Process] Meeting created: id={new_meeting.id}")

        # ------------------------------------------------------------------
        # Step 3 — LLM structured extraction (summary + decisions + actions)
        # ------------------------------------------------------------------
        logger.info("[Process] Step 3: Running AI extraction pipeline…")
        structured: dict = generate_structured_summary(transcript)
        # structured = {"summary": str, "decisions": [...], "action_items": [...]}

        # ------------------------------------------------------------------
        # Step 4 — Persist action items
        # ------------------------------------------------------------------
        logger.info("[Process] Step 4: Persisting action items…")
        saved_items = []
        for item in structured.get("action_items", []):
            # Only persist items with reasonable confidence
            if item.get("confidence_score", 1.0) < 0.4:
                logger.debug(f"[Process] Skipping low-confidence item: {item}")
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
            saved_items.append({
                "task": item.get("task"),
                "assignee": item.get("assignee"),
                "deadline": item.get("deadline"),
                "confidence_score": item.get("confidence_score"),
            })

        db.commit()
        logger.info(f"[Process] Saved {len(saved_items)} action items")

        # ------------------------------------------------------------------
        # Step 5 — Trigger n8n workflow (background, with retry)
        # ------------------------------------------------------------------
        background_tasks.add_task(
            trigger_n8n_workflow,
            db,
            new_meeting.id,
            transcript,
            {
                "summary":      structured.get("summary", ""),
                "decisions":    structured.get("decisions", []),
                "action_items": saved_items,
            },
            "meeting_processed",
        )
        logger.info("[Process] n8n trigger queued as background task")

        # ------------------------------------------------------------------
        # Step 6 — Return structured response
        # ------------------------------------------------------------------
        logger.info("[Process] Complete.")
        return {
            "status": "success",
            "meeting_id": new_meeting.id,
            "title": new_meeting.title,
            "transcript": transcript,
            "structured_output": {
                "summary": structured.get("summary", ""),
                "decisions": structured.get("decisions", []),
                "action_items": saved_items,
            },
            # Legacy field — keep for backward compatibility with frontend
            "summary": structured.get("summary", ""),
            "action_items": saved_items,
        }

    except HTTPException:
        raise
    except Exception as exc:
        error_msg = f"Processing failed: {exc}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)


# ---------------------------------------------------------------------------
# Process from raw transcript — no audio upload needed
# ---------------------------------------------------------------------------

@router.post("/process-transcript")
async def process_transcript(
    request: TranscriptProcessRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Process a meeting from a pasted transcript (no audio file required).
    Skips transcription entirely — goes straight to AI extraction.
    """
    try:
        transcript = request.transcript.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="Transcript is empty")

        logger.info(f"[ProcessTranscript] Starting for user {current_user.id}")

        # Create meeting record
        new_meeting = Meeting(
            user_id=current_user.id,
            title=request.title or "Untitled Meeting",
            audio_path=None,
            transcript=transcript,
            created_at=datetime.utcnow(),
        )
        db.add(new_meeting)
        db.commit()
        db.refresh(new_meeting)

        # AI extraction
        structured: dict = generate_structured_summary(transcript)

        # Persist action items
        saved_items = []
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
            saved_items.append({
                "task": item.get("task"),
                "assignee": item.get("assignee"),
                "deadline": item.get("deadline"),
                "confidence_score": item.get("confidence_score"),
            })
        db.commit()

        # n8n trigger
        background_tasks.add_task(
            trigger_n8n_workflow, db, new_meeting.id, transcript,
            {"summary": structured.get("summary", ""),
             "decisions": structured.get("decisions", []),
             "action_items": saved_items},
            "meeting_processed",
        )

        return {
            "status": "success",
            "meeting_id": new_meeting.id,
            "title": new_meeting.title,
            "transcript": transcript,
            "structured_output": {
                "summary": structured.get("summary", ""),
                "decisions": structured.get("decisions", []),
                "action_items": saved_items,
            },
            "summary": structured.get("summary", ""),
            "action_items": saved_items,
        }

    except HTTPException:
        raise
    except Exception as exc:
        error_msg = f"Processing failed: {exc}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

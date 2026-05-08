"""
Live Meeting WebSocket Routes
==============================

WS  /live/ws/{meeting_id}     — main WebSocket endpoint
GET /live/session/{meeting_id} — get current session state
POST /live/end/{meeting_id}    — end a live session + save final transcript
POST /live/note/{meeting_id}   — add a collaborative note
POST /live/assign/{meeting_id} — assign a task live
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import get_current_user
from backend.services.websocket_manager import manager
from backend.services.live_meeting_service import (
    get_or_create_session,
    end_session,
    process_transcript_chunk,
    add_note,
    assign_task,
    get_session_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["Live Meeting"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{meeting_id}")
async def live_meeting_ws(
    websocket: WebSocket,
    meeting_id: int,
):
    """
    Main WebSocket endpoint for live meeting collaboration.

    Client sends JSON messages:
      {"type": "auth",             "token": "JWT_TOKEN"}
      {"type": "transcript_chunk", "text": "...", "speaker": "Alice"}
      {"type": "note",             "text": "..."}
      {"type": "assign_task",      "task": "...", "assignee": "Bob", "deadline": "..."}
      {"type": "pong"}
      {"type": "end_meeting"}

    Server broadcasts:
      transcript_chunk, ai_update, suggestion, note_added,
      task_assigned, speaker_active, participant_joined,
      participant_left, snapshot_saved, ping, error
    """
    room_id   = str(meeting_id)
    user_id   = None
    user_name = "Anonymous"
    db        = SessionLocal()

    try:
        await websocket.accept()

        # Step 1 — Wait for auth message
        try:
            auth_data = await websocket.receive_json()
        except Exception:
            await websocket.send_json({"type": "error", "message": "Expected auth message"})
            await websocket.close()
            return

        if auth_data.get("type") != "auth":
            await websocket.send_json({"type": "error", "message": "First message must be auth"})
            await websocket.close()
            return

        # Validate JWT token
        token = auth_data.get("token", "")
        try:
            from backend.app.auth import decode_token
            payload = decode_token(token)
            user_id   = str(payload.get("user_id", "unknown"))
            user_name = auth_data.get("user_name", f"User {user_id}")
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close()
            return

        # Step 2 — Join room
        # Re-accept is not needed since we already accepted above
        # Register in manager directly
        manager.rooms[room_id][user_id] = websocket
        manager.user_meta[user_id] = {
            "name":      user_name,
            "room_id":   room_id,
            "joined_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }

        # Create/get live session
        session = get_or_create_session(room_id, meeting_id, int(user_id))

        # Send welcome + current state
        await websocket.send_json({
            "type":         "connected",
            "room_id":      room_id,
            "meeting_id":   meeting_id,
            "user_id":      user_id,
            "participants": manager.get_participants(room_id),
            "session":      get_session_summary(room_id),
        })

        # Notify others
        await manager.broadcast(room_id, {
            "type":         "participant_joined",
            "user_id":      user_id,
            "user_name":    user_name,
            "participants": manager.get_participants(room_id),
        }, exclude=user_id)

        # Step 3 — Message loop
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            msg_type = data.get("type", "")

            if msg_type == "transcript_chunk":
                await process_transcript_chunk(
                    room_id = room_id,
                    chunk   = data.get("text", ""),
                    speaker = data.get("speaker"),
                    db      = db,
                )

            elif msg_type == "note":
                await add_note(
                    room_id   = room_id,
                    user_id   = user_id,
                    user_name = user_name,
                    note_text = data.get("text", ""),
                )

            elif msg_type == "assign_task":
                await assign_task(
                    room_id       = room_id,
                    assigner_name = user_name,
                    task          = data.get("task", ""),
                    assignee      = data.get("assignee", ""),
                    deadline      = data.get("deadline"),
                )

            elif msg_type == "pong":
                pass  # heartbeat response

            elif msg_type == "end_meeting":
                await _finalize_meeting(room_id, meeting_id, db)
                break

            elif msg_type == "request_update":
                # Client requests current AI state
                summary = get_session_summary(room_id)
                if summary:
                    await websocket.send_json({
                        "type":    "ai_update",
                        "summary": summary.get("summary", ""),
                        "decisions": summary.get("decisions", []),
                        "action_items": summary.get("action_items", []),
                    })

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected: user={user_id} room={room_id}")
    except Exception as exc:
        logger.error(f"[WS] Error in room={room_id}: {exc}")
    finally:
        if user_id:
            await manager.disconnect(room_id, user_id)
        db.close()


async def _finalize_meeting(room_id: str, meeting_id: int, db: Session) -> None:
    """Save final transcript and broadcast completion."""
    from backend.services.live_meeting_service import _save_snapshot
    await _save_snapshot(room_id, db)

    session = end_session(room_id)
    await manager.broadcast(room_id, {
        "type":    "meeting_ended",
        "summary": session.live_summary if session else "",
    })


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/session/{meeting_id}")
async def get_live_session(
    meeting_id: int,
    current_user=Depends(get_current_user),
):
    """Get current state of a live session."""
    room_id = str(meeting_id)
    summary = get_session_summary(room_id)
    if not summary:
        return {"active": False, "meeting_id": meeting_id}
    return {"active": True, **summary}


class NoteRequest(BaseModel):
    text: str


@router.post("/note/{meeting_id}")
async def add_note_rest(
    meeting_id: int,
    request: NoteRequest,
    current_user=Depends(get_current_user),
):
    """Add a note via REST (for clients that can't use WebSocket)."""
    room_id = str(meeting_id)
    await add_note(
        room_id   = room_id,
        user_id   = str(current_user.id),
        user_name = current_user.full_name or current_user.email,
        note_text = request.text,
    )
    return {"status": "ok"}


class TaskRequest(BaseModel):
    task:     str
    assignee: str
    deadline: Optional[str] = None


@router.post("/assign/{meeting_id}")
async def assign_task_rest(
    meeting_id: int,
    request: TaskRequest,
    current_user=Depends(get_current_user),
):
    """Assign a task via REST."""
    room_id = str(meeting_id)
    await assign_task(
        room_id       = room_id,
        assigner_name = current_user.full_name or current_user.email,
        task          = request.task,
        assignee      = request.assignee,
        deadline      = request.deadline,
    )
    return {"status": "ok"}


@router.post("/end/{meeting_id}")
async def end_live_meeting(
    meeting_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """End a live meeting session and save final state."""
    room_id = str(meeting_id)
    await _finalize_meeting(room_id, meeting_id, db)
    return {"status": "ended", "meeting_id": meeting_id}

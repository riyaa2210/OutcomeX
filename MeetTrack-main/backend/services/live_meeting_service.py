"""
Live Meeting Service
=====================
Handles real-time AI processing during a live meeting session.

Features:
  - Incremental transcript accumulation
  - Streaming chunk processing (process every N words)
  - Incremental summarization (update summary as meeting progresses)
  - Live AI suggestions (missed deadlines, blockers, repeated topics)
  - Speaker activity tracking
  - Periodic transcript snapshots to DB
  - Async background processing (never blocks WebSocket)
"""

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.services.websocket_manager import manager

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_PROCESS_EVERY   = 50    # process AI update every N new words
SNAPSHOT_EVERY_SECS   = 30    # save transcript snapshot every 30s
SUGGESTION_COOLDOWN   = 60    # min seconds between same suggestion type
MAX_TRANSCRIPT_CHARS  = 50000 # cap for incremental processing


# ── In-memory session state ───────────────────────────────────────────────────

class LiveSession:
    """Holds state for one active live meeting."""

    def __init__(self, room_id: str, meeting_id: int, user_id: int):
        self.room_id         = room_id
        self.meeting_id      = meeting_id
        self.user_id         = user_id
        self.transcript      = ""
        self.word_count      = 0
        self.last_processed  = 0       # word count at last AI update
        self.last_snapshot   = datetime.now(timezone.utc)
        self.last_suggestion: dict[str, datetime] = {}
        self.speaker_activity: dict[str, int] = defaultdict(int)  # speaker → word count
        self.notes: list[dict] = []
        self.live_actions: list[dict] = []
        self.live_decisions: list[str] = []
        self.live_summary    = ""
        self.started_at      = datetime.now(timezone.utc)
        self.is_active       = True


# Global session registry
_sessions: dict[str, LiveSession] = {}


def get_or_create_session(room_id: str, meeting_id: int, user_id: int) -> LiveSession:
    if room_id not in _sessions:
        _sessions[room_id] = LiveSession(room_id, meeting_id, user_id)
        logger.info(f"[Live] Created session room={room_id} meeting={meeting_id}")
    return _sessions[room_id]


def end_session(room_id: str) -> Optional[LiveSession]:
    session = _sessions.pop(room_id, None)
    if session:
        session.is_active = False
        logger.info(f"[Live] Ended session room={room_id}")
    return session


# ── Transcript chunk processing ───────────────────────────────────────────────

async def process_transcript_chunk(
    room_id: str,
    chunk: str,
    speaker: Optional[str],
    db: Session,
) -> None:
    """
    Called when a new transcript chunk arrives via WebSocket.
    Accumulates text and triggers AI updates when enough new words arrive.
    """
    session = _sessions.get(room_id)
    if not session:
        return

    # Append chunk with speaker prefix
    if speaker:
        session.transcript += f"\n{speaker}: {chunk}"
        session.speaker_activity[speaker] += len(chunk.split())
    else:
        session.transcript += f"\n{chunk}"

    new_words = len(chunk.split())
    session.word_count += new_words

    # Broadcast transcript chunk to all room participants
    await manager.broadcast(room_id, {
        "type":      "transcript_chunk",
        "text":      chunk,
        "speaker":   speaker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "word_count": session.word_count,
    })

    # Broadcast speaker activity
    if speaker:
        await manager.broadcast(room_id, {
            "type":    "speaker_active",
            "speaker": speaker,
            "words":   session.speaker_activity[speaker],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Trigger AI update every CHUNK_PROCESS_EVERY new words
    words_since_last = session.word_count - session.last_processed
    if words_since_last >= CHUNK_PROCESS_EVERY:
        session.last_processed = session.word_count
        asyncio.create_task(_run_incremental_ai(room_id, db))

    # Periodic snapshot
    now = datetime.now(timezone.utc)
    secs_since_snapshot = (now - session.last_snapshot).total_seconds()
    if secs_since_snapshot >= SNAPSHOT_EVERY_SECS:
        session.last_snapshot = now
        asyncio.create_task(_save_snapshot(room_id, db))


# ── Incremental AI processing ─────────────────────────────────────────────────

async def _run_incremental_ai(room_id: str, db: Session) -> None:
    """
    Run AI extraction on the current transcript and broadcast updates.
    Uses the last MAX_TRANSCRIPT_CHARS chars for efficiency.
    """
    session = _sessions.get(room_id)
    if not session:
        return

    transcript_slice = session.transcript[-MAX_TRANSCRIPT_CHARS:]

    try:
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _extract_live_insights,
            transcript_slice,
        )

        if not result:
            return

        # Update session state
        session.live_summary   = result.get("summary", session.live_summary)
        session.live_decisions = result.get("decisions", session.live_decisions)
        session.live_actions   = result.get("action_items", session.live_actions)

        # Broadcast AI update
        await manager.broadcast(room_id, {
            "type":         "ai_update",
            "summary":      session.live_summary,
            "decisions":    session.live_decisions,
            "action_items": session.live_actions,
            "word_count":   session.word_count,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        })

        # Check for live suggestions
        await _check_suggestions(room_id, session, result)

    except Exception as exc:
        logger.error(f"[Live] AI update failed for room={room_id}: {exc}")


def _extract_live_insights(transcript: str) -> Optional[dict]:
    """
    Synchronous AI extraction — runs in thread pool.
    Uses summary_service for structured output.
    """
    try:
        from backend.services.summary_service import generate_structured_summary
        result = generate_structured_summary(transcript)
        return result
    except Exception as exc:
        logger.error(f"[Live] Insight extraction error: {exc}")
        return None


# ── Live AI suggestions ───────────────────────────────────────────────────────

async def _check_suggestions(
    room_id: str,
    session: LiveSession,
    result: dict,
) -> None:
    """
    Analyse current meeting state and broadcast AI suggestions:
      - Missed deadlines (action items without deadlines)
      - Unresolved blockers
      - Repeated discussion topics
    """
    now = datetime.now(timezone.utc)
    suggestions = []

    # 1. Action items without assignees
    unassigned = [
        a for a in result.get("action_items", [])
        if not a.get("assignee") or a.get("assignee") == "Unassigned"
    ]
    if unassigned and _can_suggest(session, "unassigned", now):
        suggestions.append({
            "type":    "unassigned_tasks",
            "message": f"{len(unassigned)} action item(s) have no assignee. Consider assigning them now.",
            "items":   [a.get("task", "") for a in unassigned[:3]],
            "severity": "warning",
        })
        session.last_suggestion["unassigned"] = now

    # 2. Action items without deadlines
    no_deadline = [
        a for a in result.get("action_items", [])
        if not a.get("deadline")
    ]
    if len(no_deadline) >= 3 and _can_suggest(session, "no_deadline", now):
        suggestions.append({
            "type":    "missing_deadlines",
            "message": f"{len(no_deadline)} tasks have no deadline. Setting deadlines improves accountability.",
            "severity": "info",
        })
        session.last_suggestion["no_deadline"] = now

    # 3. Blocker detection
    blocker_pattern = re.compile(
        r"\b(blocked|waiting on|depends on|can'?t proceed|stuck)\b",
        re.IGNORECASE
    )
    recent_text = session.transcript[-2000:]
    if blocker_pattern.search(recent_text) and _can_suggest(session, "blocker", now):
        suggestions.append({
            "type":    "blocker_detected",
            "message": "A blocker was mentioned. Make sure it's tracked as an action item.",
            "severity": "warning",
        })
        session.last_suggestion["blocker"] = now

    # 4. Long meeting without decisions
    meeting_mins = (now - session.started_at).total_seconds() / 60
    if meeting_mins > 20 and not result.get("decisions") and _can_suggest(session, "no_decisions", now):
        suggestions.append({
            "type":    "no_decisions",
            "message": "20+ minutes in with no recorded decisions. Consider summarising key agreements.",
            "severity": "info",
        })
        session.last_suggestion["no_decisions"] = now

    # Broadcast suggestions
    for suggestion in suggestions:
        await manager.broadcast(room_id, {
            "type":      "suggestion",
            "timestamp": now.isoformat(),
            **suggestion,
        })


def _can_suggest(session: LiveSession, suggestion_type: str, now: datetime) -> bool:
    """Rate-limit suggestions to avoid spamming."""
    last = session.last_suggestion.get(suggestion_type)
    if not last:
        return True
    return (now - last).total_seconds() >= SUGGESTION_COOLDOWN


# ── Snapshot saving ───────────────────────────────────────────────────────────

async def _save_snapshot(room_id: str, db: Session) -> None:
    """Save current transcript to DB as a snapshot."""
    session = _sessions.get(room_id)
    if not session or not session.transcript.strip():
        return

    try:
        from backend.models.meeting import Meeting
        meeting = db.query(Meeting).filter(Meeting.id == session.meeting_id).first()
        if meeting:
            meeting.transcript = session.transcript
            db.commit()
            logger.info(f"[Live] Snapshot saved for meeting={session.meeting_id}")

            await manager.broadcast(room_id, {
                "type":      "snapshot_saved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "chars":     len(session.transcript),
            })
    except Exception as exc:
        logger.error(f"[Live] Snapshot save failed: {exc}")


# ── Collaborative notes ───────────────────────────────────────────────────────

async def add_note(
    room_id: str,
    user_id: str,
    user_name: str,
    note_text: str,
) -> None:
    """Add a collaborative note and broadcast to room."""
    session = _sessions.get(room_id)
    if not session:
        return

    note = {
        "id":        len(session.notes) + 1,
        "user_id":   user_id,
        "user_name": user_name,
        "text":      note_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    session.notes.append(note)

    await manager.broadcast(room_id, {
        "type": "note_added",
        **note,
    })


async def assign_task(
    room_id: str,
    assigner_name: str,
    task: str,
    assignee: str,
    deadline: Optional[str] = None,
) -> None:
    """Broadcast a task assignment to the room."""
    await manager.broadcast(room_id, {
        "type":         "task_assigned",
        "task":         task,
        "assignee":     assignee,
        "deadline":     deadline,
        "assigned_by":  assigner_name,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    })


# ── Session summary ───────────────────────────────────────────────────────────

def get_session_summary(room_id: str) -> Optional[dict]:
    """Get current state of a live session."""
    session = _sessions.get(room_id)
    if not session:
        return None

    duration_mins = (datetime.now(timezone.utc) - session.started_at).total_seconds() / 60

    return {
        "room_id":         room_id,
        "meeting_id":      session.meeting_id,
        "is_active":       session.is_active,
        "word_count":      session.word_count,
        "duration_mins":   round(duration_mins, 1),
        "participants":    manager.get_participants(room_id),
        "speaker_activity": dict(session.speaker_activity),
        "notes_count":     len(session.notes),
        "action_items":    session.live_actions,
        "decisions":       session.live_decisions,
        "summary":         session.live_summary,
    }

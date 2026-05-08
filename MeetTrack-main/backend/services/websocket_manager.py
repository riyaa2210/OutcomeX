"""
WebSocket Connection Manager
=============================
Manages all active WebSocket connections per meeting room.

Architecture:
  - Each meeting has a "room" identified by meeting_id
  - Multiple users can join the same room (collaborative)
  - Messages are broadcast to all room members
  - Reconnect support via token-based auth on connect
  - Heartbeat ping/pong to detect dead connections

Room events:
  transcript_chunk    — new text from live transcription
  ai_update           — incremental summary/decisions/actions
  suggestion          — AI-generated live suggestion
  note_added          — collaborative note from a participant
  task_assigned       — task assigned to someone
  speaker_active      — speaker activity update
  participant_joined  — user joined the room
  participant_left    — user left the room
  snapshot_saved      — periodic transcript snapshot saved
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Thread-safe WebSocket connection manager.
    Supports per-room broadcasting and individual messaging.
    """

    def __init__(self):
        # room_id → {user_id: WebSocket}
        self.rooms: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        # user_id → metadata
        self.user_meta: dict[str, dict] = {}
        # room_id → last activity timestamp
        self.room_activity: dict[str, datetime] = {}

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        user_id: str,
        user_name: str = "Anonymous",
    ) -> None:
        await websocket.accept()
        self.rooms[room_id][user_id] = websocket
        self.user_meta[user_id] = {
            "name":      user_name,
            "room_id":   room_id,
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }
        self.room_activity[room_id] = datetime.now(timezone.utc)

        logger.info(f"[WS] {user_name} joined room={room_id} (total={len(self.rooms[room_id])})")

        # Notify others
        await self.broadcast(room_id, {
            "type":      "participant_joined",
            "user_id":   user_id,
            "user_name": user_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "participants": self.get_participants(room_id),
        }, exclude=user_id)

    async def disconnect(self, room_id: str, user_id: str) -> None:
        user_name = self.user_meta.get(user_id, {}).get("name", "Unknown")

        if room_id in self.rooms and user_id in self.rooms[room_id]:
            del self.rooms[room_id][user_id]
            if not self.rooms[room_id]:
                del self.rooms[room_id]

        self.user_meta.pop(user_id, None)

        logger.info(f"[WS] {user_name} left room={room_id}")

        # Notify others
        if room_id in self.rooms:
            await self.broadcast(room_id, {
                "type":         "participant_left",
                "user_id":      user_id,
                "user_name":    user_name,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "participants": self.get_participants(room_id),
            })

    # ── Messaging ─────────────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send a message to a specific user. Returns False if not connected."""
        for room in self.rooms.values():
            if user_id in room:
                try:
                    await room[user_id].send_json(message)
                    return True
                except Exception as exc:
                    logger.warning(f"[WS] Failed to send to user={user_id}: {exc}")
                    return False
        return False

    async def broadcast(
        self,
        room_id: str,
        message: dict,
        exclude: Optional[str] = None,
    ) -> None:
        """Broadcast a message to all users in a room."""
        if room_id not in self.rooms:
            return

        dead_connections = []
        for user_id, ws in list(self.rooms[room_id].items()):
            if user_id == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(f"[WS] Dead connection user={user_id}: {exc}")
                dead_connections.append(user_id)

        # Clean up dead connections
        for uid in dead_connections:
            await self.disconnect(room_id, uid)

        self.room_activity[room_id] = datetime.now(timezone.utc)

    async def broadcast_to_all(self, message: dict) -> None:
        """Broadcast to every connected user across all rooms."""
        for room_id in list(self.rooms.keys()):
            await self.broadcast(room_id, message)

    # ── Room info ─────────────────────────────────────────────────────────────

    def get_participants(self, room_id: str) -> list[dict]:
        if room_id not in self.rooms:
            return []
        return [
            {
                "user_id":   uid,
                "user_name": self.user_meta.get(uid, {}).get("name", "Unknown"),
                "joined_at": self.user_meta.get(uid, {}).get("joined_at"),
            }
            for uid in self.rooms[room_id]
        ]

    def room_exists(self, room_id: str) -> bool:
        return room_id in self.rooms and len(self.rooms[room_id]) > 0

    def get_room_count(self) -> int:
        return len(self.rooms)

    def get_total_connections(self) -> int:
        return sum(len(users) for users in self.rooms.values())

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    async def ping_all(self) -> None:
        """Send ping to all connections to detect dead sockets."""
        ping_msg = {"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()}
        await self.broadcast_to_all(ping_msg)


# Singleton instance
manager = ConnectionManager()

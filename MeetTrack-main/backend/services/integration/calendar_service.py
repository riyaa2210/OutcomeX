"""
Calendar & Meeting Platform Service
=====================================
Fetches meetings, recordings, and participants from:
  - Google Calendar / Google Meet
  - Zoom
  - Microsoft Teams (via Graph API)

All methods return a normalised ExternalMeeting-compatible dict.
Deduplication is enforced via external_id + provider unique index.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from backend.models.integration import (
    OAuthToken, ExternalMeeting, IntegrationProvider,
    IntegrationAuditLog, AuditAction,
)
from backend.services.integration.oauth_service import get_access_token_plain, _audit

logger = logging.getLogger(__name__)


# ── Google Calendar ───────────────────────────────────────────────────────────

def fetch_google_calendar_events(
    db: Session,
    user_id: int,
    days_ahead: int = 7,
    days_back: int = 30,
) -> list[dict]:
    """Fetch upcoming and recent Google Calendar events."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.GOOGLE_CALENDAR)
    if not access_token:
        return []

    now    = datetime.now(timezone.utc)
    t_min  = (now - timedelta(days=days_back)).isoformat()
    t_max  = (now + timedelta(days=days_ahead)).isoformat()

    try:
        resp = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin":      t_min,
                "timeMax":      t_max,
                "singleEvents": True,
                "orderBy":      "startTime",
                "maxResults":   50,
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        events = []
        for item in items:
            start = item.get("start", {})
            end   = item.get("end", {})
            start_dt = _parse_dt(start.get("dateTime") or start.get("date"))
            end_dt   = _parse_dt(end.get("dateTime")   or end.get("date"))

            # Extract Meet link
            meet_url = None
            conf_data = item.get("conferenceData", {})
            for ep in conf_data.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_url = ep.get("uri")
                    break

            participants = [
                {"name": a.get("displayName", ""), "email": a.get("email", "")}
                for a in item.get("attendees", [])
            ]

            events.append({
                "external_id":     item["id"],
                "provider":        "google_calendar",
                "title":           item.get("summary", "Untitled"),
                "description":     item.get("description", ""),
                "start_time":      start_dt,
                "end_time":        end_dt,
                "duration_mins":   _duration_mins(start_dt, end_dt),
                "meeting_url":     meet_url or item.get("htmlLink"),
                "recording_url":   None,
                "participants":    participants,
                "organizer_email": item.get("organizer", {}).get("email"),
                "raw_data":        item,
            })

        _audit(db, user_id, "google_calendar", AuditAction.SYNC_MEETINGS,
               details={"count": len(events)})
        return events

    except Exception as exc:
        logger.error(f"[Calendar] Google Calendar fetch failed: {exc}")
        _audit(db, user_id, "google_calendar", AuditAction.SYNC_MEETINGS,
               success=False, error=str(exc))
        return []


# ── Zoom ──────────────────────────────────────────────────────────────────────

def fetch_zoom_meetings(
    db: Session,
    user_id: int,
    include_recordings: bool = True,
) -> list[dict]:
    """Fetch Zoom meetings and recordings."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.ZOOM)
    if not access_token:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    events  = []

    try:
        # Upcoming meetings
        resp = requests.get(
            "https://api.zoom.us/v2/users/me/meetings",
            headers=headers,
            params={"type": "scheduled", "page_size": 30},
            timeout=15,
        )
        resp.raise_for_status()
        for m in resp.json().get("meetings", []):
            start_dt = _parse_dt(m.get("start_time"))
            dur_mins = m.get("duration", 0)
            end_dt   = (start_dt + timedelta(minutes=dur_mins)) if start_dt else None

            events.append({
                "external_id":     str(m["id"]),
                "provider":        "zoom",
                "title":           m.get("topic", "Zoom Meeting"),
                "description":     m.get("agenda", ""),
                "start_time":      start_dt,
                "end_time":        end_dt,
                "duration_mins":   dur_mins,
                "meeting_url":     m.get("join_url"),
                "recording_url":   None,
                "participants":    [],
                "organizer_email": m.get("host_email"),
                "raw_data":        m,
            })

        # Past recordings
        if include_recordings:
            from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
            rec_resp  = requests.get(
                "https://api.zoom.us/v2/users/me/recordings",
                headers=headers,
                params={"from": from_date, "page_size": 20},
                timeout=15,
            )
            if rec_resp.ok:
                for m in rec_resp.json().get("meetings", []):
                    rec_files = m.get("recording_files", [])
                    rec_url   = next(
                        (f.get("download_url") for f in rec_files if f.get("file_type") == "MP4"),
                        None,
                    )
                    start_dt = _parse_dt(m.get("start_time"))
                    dur_mins = m.get("duration", 0)
                    end_dt   = (start_dt + timedelta(minutes=dur_mins)) if start_dt else None

                    events.append({
                        "external_id":     str(m["uuid"]),
                        "provider":        "zoom",
                        "title":           m.get("topic", "Zoom Recording"),
                        "description":     "",
                        "start_time":      start_dt,
                        "end_time":        end_dt,
                        "duration_mins":   dur_mins,
                        "meeting_url":     m.get("share_url"),
                        "recording_url":   rec_url,
                        "participants":    _zoom_participants(headers, str(m["id"])),
                        "organizer_email": m.get("host_email"),
                        "raw_data":        m,
                    })

        _audit(db, user_id, "zoom", AuditAction.SYNC_MEETINGS, details={"count": len(events)})
        return events

    except Exception as exc:
        logger.error(f"[Calendar] Zoom fetch failed: {exc}")
        _audit(db, user_id, "zoom", AuditAction.SYNC_MEETINGS, success=False, error=str(exc))
        return []


def _zoom_participants(headers: dict, meeting_id: str) -> list[dict]:
    """Fetch participant list for a Zoom meeting."""
    try:
        resp = requests.get(
            f"https://api.zoom.us/v2/report/meetings/{meeting_id}/participants",
            headers=headers,
            params={"page_size": 50},
            timeout=10,
        )
        if resp.ok:
            return [
                {"name": p.get("name", ""), "email": p.get("user_email", "")}
                for p in resp.json().get("participants", [])
            ]
    except Exception:
        pass
    return []


# ── Microsoft Teams ───────────────────────────────────────────────────────────

def fetch_teams_meetings(
    db: Session,
    user_id: int,
    days_ahead: int = 7,
    days_back: int = 30,
) -> list[dict]:
    """Fetch Microsoft Teams meetings via Graph API."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.MICROSOFT_TEAMS)
    if not access_token:
        return []

    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "startDateTime": start,
                "endDateTime":   end,
                "$top":          50,
                "$select":       "id,subject,start,end,onlineMeeting,attendees,organizer,bodyPreview",
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])

        events = []
        for item in items:
            start_dt = _parse_dt(item.get("start", {}).get("dateTime"))
            end_dt   = _parse_dt(item.get("end",   {}).get("dateTime"))
            om       = item.get("onlineMeeting") or {}

            participants = [
                {
                    "name":  a.get("emailAddress", {}).get("name", ""),
                    "email": a.get("emailAddress", {}).get("address", ""),
                }
                for a in item.get("attendees", [])
            ]

            events.append({
                "external_id":     item["id"],
                "provider":        "microsoft_teams",
                "title":           item.get("subject", "Teams Meeting"),
                "description":     item.get("bodyPreview", ""),
                "start_time":      start_dt,
                "end_time":        end_dt,
                "duration_mins":   _duration_mins(start_dt, end_dt),
                "meeting_url":     om.get("joinUrl"),
                "recording_url":   None,
                "participants":    participants,
                "organizer_email": item.get("organizer", {}).get("emailAddress", {}).get("address"),
                "raw_data":        item,
            })

        _audit(db, user_id, "microsoft_teams", AuditAction.SYNC_MEETINGS,
               details={"count": len(events)})
        return events

    except Exception as exc:
        logger.error(f"[Calendar] Teams fetch failed: {exc}")
        _audit(db, user_id, "microsoft_teams", AuditAction.SYNC_MEETINGS,
               success=False, error=str(exc))
        return []


# ── Sync to DB ────────────────────────────────────────────────────────────────

def sync_external_meetings(
    db: Session,
    user_id: int,
    events: list[dict],
) -> dict:
    """
    Upsert external meetings into the DB.
    Returns {"new": int, "updated": int, "skipped": int}
    """
    new = updated = skipped = 0

    for ev in events:
        external_id = ev.get("external_id")
        provider    = ev.get("provider")
        if not external_id or not provider:
            skipped += 1
            continue

        existing = db.query(ExternalMeeting).filter(
            ExternalMeeting.external_id == external_id,
            ExternalMeeting.provider    == provider,
        ).first()

        if existing:
            # Update recording URL if newly available
            if ev.get("recording_url") and not existing.recording_url:
                existing.recording_url = ev["recording_url"]
                existing.processing_status = "pending"
                db.commit()
                updated += 1
            else:
                skipped += 1
            continue

        em = ExternalMeeting(
            user_id         = user_id,
            provider        = provider,
            external_id     = external_id,
            title           = ev.get("title", ""),
            description     = ev.get("description", ""),
            start_time      = ev.get("start_time"),
            end_time        = ev.get("end_time"),
            duration_mins   = ev.get("duration_mins"),
            meeting_url     = ev.get("meeting_url"),
            recording_url   = ev.get("recording_url"),
            participants    = ev.get("participants", []),
            organizer_email = ev.get("organizer_email"),
            raw_data        = ev.get("raw_data"),
            processing_status = "pending",
        )
        db.add(em)
        new += 1

    db.commit()
    return {"new": new, "updated": updated, "skipped": skipped}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handle date-only strings
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _duration_mins(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if start and end:
        return max(0, int((end - start).total_seconds() / 60))
    return None

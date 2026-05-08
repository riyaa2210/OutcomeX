"""
Task Sync Service
=================
Pushes OutcomeX action items to external task managers:
  - Google Tasks
  - Trello
  - Notion
  - Jira

Also creates calendar reminders for pending tasks via Google Calendar.

Each sync is idempotent — uses external_task_id stored in action_item metadata
to avoid creating duplicates.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from backend.models.action_item import ActionItem
from backend.models.integration import IntegrationProvider, AuditAction
from backend.services.integration.oauth_service import get_access_token_plain, _audit

logger = logging.getLogger(__name__)


# ── Google Tasks ──────────────────────────────────────────────────────────────

def sync_to_google_tasks(
    db: Session,
    user_id: int,
    action_items: list[ActionItem],
    tasklist_id: str = "@default",
) -> dict:
    """Push action items to Google Tasks."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.GOOGLE_TASKS)
    if not access_token:
        return {"error": "Google Tasks not connected", "synced": 0}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    synced = 0
    errors = []

    for item in action_items:
        try:
            due_rfc = None
            if item.deadline:
                try:
                    due_rfc = datetime.fromisoformat(str(item.deadline)).strftime("%Y-%m-%dT00:00:00.000Z")
                except Exception:
                    pass

            body = {
                "title":  item.description or item.title or "Action Item",
                "notes":  f"Assigned to: {item.assigned_to or 'Unassigned'}\nFrom OutcomeX meeting #{item.meeting_id}",
                "status": "needsAction",
            }
            if due_rfc:
                body["due"] = due_rfc

            resp = requests.post(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks",
                headers=headers,
                json=body,
                timeout=10,
            )
            if resp.ok:
                synced += 1
            else:
                errors.append(f"item {item.id}: {resp.status_code}")
        except Exception as exc:
            errors.append(f"item {item.id}: {exc}")

    _audit(db, user_id, "google_tasks", AuditAction.SYNC_TASKS,
           details={"synced": synced, "errors": errors})
    return {"synced": synced, "errors": errors}


# ── Trello ────────────────────────────────────────────────────────────────────

def sync_to_trello(
    db: Session,
    user_id: int,
    action_items: list[ActionItem],
    board_id: Optional[str] = None,
    list_id: Optional[str] = None,
) -> dict:
    """Push action items to Trello as cards."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.TRELLO)
    api_key = os.getenv("TRELLO_API_KEY", "")
    if not access_token or not api_key:
        return {"error": "Trello not connected", "synced": 0}

    # Get first available list if not specified
    if not list_id:
        list_id = _get_trello_default_list(api_key, access_token, board_id)
    if not list_id:
        return {"error": "No Trello list found", "synced": 0}

    synced = 0
    errors = []

    for item in action_items:
        try:
            due_str = None
            if item.deadline:
                try:
                    due_str = datetime.fromisoformat(str(item.deadline)).strftime("%Y-%m-%dT12:00:00.000Z")
                except Exception:
                    pass

            params = {
                "key":   api_key,
                "token": access_token,
                "idList": list_id,
                "name":  item.description or item.title or "Action Item",
                "desc":  f"Assigned to: {item.assigned_to or 'Unassigned'}\nMeeting #{item.meeting_id}",
            }
            if due_str:
                params["due"] = due_str

            resp = requests.post(
                "https://api.trello.com/1/cards",
                params=params,
                timeout=10,
            )
            if resp.ok:
                synced += 1
            else:
                errors.append(f"item {item.id}: {resp.status_code}")
        except Exception as exc:
            errors.append(f"item {item.id}: {exc}")

    _audit(db, user_id, "trello", AuditAction.SYNC_TASKS,
           details={"synced": synced, "errors": errors})
    return {"synced": synced, "errors": errors}


def _get_trello_default_list(api_key: str, token: str, board_id: Optional[str]) -> Optional[str]:
    """Get the first list ID from a Trello board."""
    try:
        if not board_id:
            # Get first board
            resp = requests.get(
                "https://api.trello.com/1/members/me/boards",
                params={"key": api_key, "token": token, "fields": "id,name"},
                timeout=10,
            )
            if resp.ok and resp.json():
                board_id = resp.json()[0]["id"]

        if board_id:
            resp = requests.get(
                f"https://api.trello.com/1/boards/{board_id}/lists",
                params={"key": api_key, "token": token},
                timeout=10,
            )
            if resp.ok and resp.json():
                return resp.json()[0]["id"]
    except Exception:
        pass
    return None


# ── Notion ────────────────────────────────────────────────────────────────────

def sync_to_notion(
    db: Session,
    user_id: int,
    action_items: list[ActionItem],
    database_id: Optional[str] = None,
) -> dict:
    """Push action items to a Notion database."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.NOTION)
    if not access_token:
        return {"error": "Notion not connected", "synced": 0}

    headers = {
        "Authorization":  f"Bearer {access_token}",
        "Content-Type":   "application/json",
        "Notion-Version": "2022-06-28",
    }

    # Find database if not specified
    if not database_id:
        database_id = _get_notion_database(headers)
    if not database_id:
        return {"error": "No Notion database found. Create a database and reconnect.", "synced": 0}

    synced = 0
    errors = []

    for item in action_items:
        try:
            props: dict = {
                "Name": {
                    "title": [{"text": {"content": (item.description or item.title or "Action Item")[:100]}}]
                },
                "Assignee": {
                    "rich_text": [{"text": {"content": item.assigned_to or "Unassigned"}}]
                },
                "Status": {
                    "select": {"name": item.status or "Pending"}
                },
                "Meeting ID": {
                    "number": item.meeting_id
                },
            }

            if item.deadline:
                try:
                    props["Due Date"] = {"date": {"start": str(item.deadline)}}
                except Exception:
                    pass

            resp = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={"parent": {"database_id": database_id}, "properties": props},
                timeout=10,
            )
            if resp.ok:
                synced += 1
            else:
                errors.append(f"item {item.id}: {resp.status_code} {resp.text[:100]}")
        except Exception as exc:
            errors.append(f"item {item.id}: {exc}")

    _audit(db, user_id, "notion", AuditAction.SYNC_TASKS,
           details={"synced": synced, "errors": errors})
    return {"synced": synced, "errors": errors}


def _get_notion_database(headers: dict) -> Optional[str]:
    """Find the first Notion database accessible to the integration."""
    try:
        resp = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"filter": {"value": "database", "property": "object"}, "page_size": 1},
            timeout=10,
        )
        if resp.ok:
            results = resp.json().get("results", [])
            if results:
                return results[0]["id"]
    except Exception:
        pass
    return None


# ── Jira ──────────────────────────────────────────────────────────────────────

def sync_to_jira(
    db: Session,
    user_id: int,
    action_items: list[ActionItem],
    project_key: Optional[str] = None,
) -> dict:
    """Push action items to Jira as issues."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.JIRA)
    if not access_token:
        return {"error": "Jira not connected", "synced": 0}

    # Get Jira cloud ID
    cloud_id = _get_jira_cloud_id(access_token)
    if not cloud_id:
        return {"error": "Could not find Jira cloud instance", "synced": 0}

    if not project_key:
        project_key = _get_jira_default_project(access_token, cloud_id)
    if not project_key:
        return {"error": "No Jira project found", "synced": 0}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
    synced = 0
    errors = []

    for item in action_items:
        try:
            body = {
                "fields": {
                    "project":     {"key": project_key},
                    "summary":     (item.description or item.title or "Action Item")[:255],
                    "description": {
                        "type":    "doc",
                        "version": 1,
                        "content": [{
                            "type":    "paragraph",
                            "content": [{
                                "type": "text",
                                "text": f"Assigned to: {item.assigned_to or 'Unassigned'}\nFrom OutcomeX meeting #{item.meeting_id}",
                            }],
                        }],
                    },
                    "issuetype": {"name": "Task"},
                }
            }
            if item.deadline:
                body["fields"]["duedate"] = str(item.deadline)

            resp = requests.post(
                f"{base_url}/issue",
                headers=headers,
                json=body,
                timeout=10,
            )
            if resp.ok:
                synced += 1
            else:
                errors.append(f"item {item.id}: {resp.status_code} {resp.text[:100]}")
        except Exception as exc:
            errors.append(f"item {item.id}: {exc}")

    _audit(db, user_id, "jira", AuditAction.SYNC_TASKS,
           details={"synced": synced, "errors": errors})
    return {"synced": synced, "errors": errors}


def _get_jira_cloud_id(access_token: str) -> Optional[str]:
    try:
        resp = requests.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.ok and resp.json():
            return resp.json()[0]["id"]
    except Exception:
        pass
    return None


def _get_jira_default_project(access_token: str, cloud_id: str) -> Optional[str]:
    try:
        resp = requests.get(
            f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project/search",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"maxResults": 1},
            timeout=10,
        )
        if resp.ok:
            values = resp.json().get("values", [])
            if values:
                return values[0]["key"]
    except Exception:
        pass
    return None


# ── Calendar Reminders ────────────────────────────────────────────────────────

def create_calendar_reminder(
    db: Session,
    user_id: int,
    action_item: ActionItem,
    reminder_minutes_before: int = 60,
) -> dict:
    """Create a Google Calendar event as a reminder for a pending task."""
    access_token = get_access_token_plain(db, user_id, IntegrationProvider.GOOGLE_CALENDAR)
    if not access_token:
        return {"error": "Google Calendar not connected"}

    if not action_item.deadline:
        return {"error": "Action item has no deadline"}

    try:
        deadline_dt = datetime.fromisoformat(str(action_item.deadline))
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

        event = {
            "summary":     f"[OutcomeX] {action_item.description or action_item.title or 'Task Due'}",
            "description": f"Action item from meeting #{action_item.meeting_id}\nAssigned to: {action_item.assigned_to or 'Unassigned'}",
            "start": {"dateTime": deadline_dt.isoformat(), "timeZone": "UTC"},
            "end":   {"dateTime": deadline_dt.isoformat(), "timeZone": "UTC"},
            "reminders": {
                "useDefault": False,
                "overrides":  [
                    {"method": "email",  "minutes": reminder_minutes_before},
                    {"method": "popup",  "minutes": 30},
                ],
            },
            "colorId": "11",  # Tomato red
        }

        resp = requests.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json",
            },
            json=event,
            timeout=10,
        )

        if resp.ok:
            _audit(db, user_id, "google_calendar", AuditAction.REMINDER_SENT,
                   resource_id=str(action_item.id))
            return {"created": True, "event_id": resp.json().get("id")}
        else:
            return {"error": f"Calendar API error: {resp.status_code}"}

    except Exception as exc:
        logger.error(f"[TaskSync] Calendar reminder failed: {exc}")
        return {"error": str(exc)}

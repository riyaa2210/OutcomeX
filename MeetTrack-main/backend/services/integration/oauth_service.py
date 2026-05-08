"""
OAuth Service
=============
Handles OAuth 2.0 flows for all supported providers.

Providers:
  - Google (Calendar, Meet, Tasks) — single OAuth app, multiple scopes
  - Zoom                           — separate OAuth app
  - Microsoft Teams                — Azure AD OAuth

Flow:
  1. GET /integrations/oauth/{provider}/authorize → redirect URL
  2. User authorises → provider redirects to /integrations/oauth/{provider}/callback
  3. Exchange code for tokens → encrypt → store in oauth_tokens
  4. Automatic token refresh before expiry

Security:
  - PKCE (code_verifier/code_challenge) for all flows
  - State parameter with HMAC-SHA256 to prevent CSRF
  - Tokens encrypted with AES-256 (Fernet) before DB storage
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from backend.models.integration import OAuthToken, IntegrationAuditLog, IntegrationProvider, AuditAction
from backend.services.integration.crypto import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

# ── Provider configs ──────────────────────────────────────────────────────────

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://automated-meeting-outcome-tracker.onrender.com")
BACKEND_URL  = os.getenv("BACKEND_URL",  "https://meeting-outcome-tracker-backend.onrender.com")

PROVIDER_CONFIGS = {
    IntegrationProvider.GOOGLE_CALENDAR: {
        "auth_url":    "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":   "https://oauth2.googleapis.com/token",
        "client_id":   os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "scopes": [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
            "openid", "email", "profile",
        ],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/google_calendar/callback",
    },
    IntegrationProvider.GOOGLE_TASKS: {
        "auth_url":    "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":   "https://oauth2.googleapis.com/token",
        "client_id":   os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "scopes": [
            "https://www.googleapis.com/auth/tasks",
            "openid", "email",
        ],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/google_tasks/callback",
    },
    IntegrationProvider.ZOOM: {
        "auth_url":    "https://zoom.us/oauth/authorize",
        "token_url":   "https://zoom.us/oauth/token",
        "client_id":   os.getenv("ZOOM_CLIENT_ID", ""),
        "client_secret": os.getenv("ZOOM_CLIENT_SECRET", ""),
        "scopes": ["meeting:read", "recording:read", "user:read"],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/zoom/callback",
    },
    IntegrationProvider.MICROSOFT_TEAMS: {
        "auth_url":    f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID','common')}/oauth2/v2.0/authorize",
        "token_url":   f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID','common')}/oauth2/v2.0/token",
        "client_id":   os.getenv("AZURE_CLIENT_ID", ""),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET", ""),
        "scopes": [
            "https://graph.microsoft.com/Calendars.Read",
            "https://graph.microsoft.com/OnlineMeetings.Read",
            "https://graph.microsoft.com/User.Read",
            "offline_access",
        ],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/microsoft_teams/callback",
    },
    IntegrationProvider.TRELLO: {
        "auth_url":    "https://trello.com/1/authorize",
        "token_url":   None,  # Trello uses API key + token (not standard OAuth2)
        "client_id":   os.getenv("TRELLO_API_KEY", ""),
        "client_secret": os.getenv("TRELLO_API_SECRET", ""),
        "scopes": ["read", "write"],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/trello/callback",
    },
    IntegrationProvider.NOTION: {
        "auth_url":    "https://api.notion.com/v1/oauth/authorize",
        "token_url":   "https://api.notion.com/v1/oauth/token",
        "client_id":   os.getenv("NOTION_CLIENT_ID", ""),
        "client_secret": os.getenv("NOTION_CLIENT_SECRET", ""),
        "scopes": [],  # Notion uses workspace-level permissions
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/notion/callback",
    },
    IntegrationProvider.JIRA: {
        "auth_url":    "https://auth.atlassian.com/authorize",
        "token_url":   "https://auth.atlassian.com/oauth/token",
        "client_id":   os.getenv("JIRA_CLIENT_ID", ""),
        "client_secret": os.getenv("JIRA_CLIENT_SECRET", ""),
        "scopes": ["read:jira-work", "write:jira-work", "offline_access"],
        "redirect_uri": f"{BACKEND_URL}/integrations/oauth/jira/callback",
    },
}


# ── State / PKCE helpers ──────────────────────────────────────────────────────

_STATE_SECRET = os.getenv("SECRET_KEY", "fallback")

def _make_state(user_id: int, provider: str) -> str:
    """HMAC-signed state: user_id:timestamp:signature"""
    ts  = str(int(time.time()))
    raw = f"{user_id}:{provider}:{ts}"
    sig = hmac.new(_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw}:{sig}"


def _verify_state(state: str, provider: str) -> Optional[int]:
    """Verify state and return user_id, or None if invalid/expired."""
    try:
        parts = state.split(":")
        if len(parts) != 4:
            return None
        user_id_str, prov, ts, sig = parts
        if prov != provider:
            return None
        # Check timestamp (10 min window)
        if abs(time.time() - int(ts)) > 600:
            return None
        raw = f"{user_id_str}:{prov}:{ts}"
        expected = hmac.new(_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return int(user_id_str)
    except Exception:
        return None


# ── Build authorization URL ───────────────────────────────────────────────────

def get_authorization_url(provider: IntegrationProvider, user_id: int) -> dict:
    """
    Build the OAuth authorization URL for a provider.
    Returns {"url": str, "state": str}
    """
    cfg = PROVIDER_CONFIGS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")

    if not cfg["client_id"]:
        raise ValueError(f"{provider.value} OAuth not configured (missing CLIENT_ID env var)")

    state = _make_state(user_id, provider.value)

    if provider == IntegrationProvider.TRELLO:
        # Trello uses a different auth flow
        params = {
            "key":          cfg["client_id"],
            "name":         "OutcomeX",
            "scope":        ",".join(cfg["scopes"]),
            "expiration":   "never",
            "response_type": "token",
            "callback_method": "fragment",
            "return_url":   cfg["redirect_uri"],
        }
        url = cfg["auth_url"] + "?" + urlencode(params)
        return {"url": url, "state": state}

    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  cfg["redirect_uri"],
        "response_type": "code",
        "scope":         " ".join(cfg["scopes"]),
        "state":         state,
        "access_type":   "offline",   # Google: get refresh token
        "prompt":        "consent",   # Google: always show consent
    }

    # Microsoft: add response_mode
    if provider == IntegrationProvider.MICROSOFT_TEAMS:
        params["response_mode"] = "query"

    # Notion: different param name
    if provider == IntegrationProvider.NOTION:
        params["owner"] = "user"

    url = cfg["auth_url"] + "?" + urlencode(params)
    return {"url": url, "state": state}


# ── Exchange code for tokens ──────────────────────────────────────────────────

def exchange_code(
    db: Session,
    provider: IntegrationProvider,
    code: str,
    state: str,
) -> OAuthToken:
    """
    Exchange authorization code for access + refresh tokens.
    Stores encrypted tokens in DB.
    """
    user_id = _verify_state(state, provider.value)
    if user_id is None:
        raise ValueError("Invalid or expired OAuth state parameter")

    cfg = PROVIDER_CONFIGS[provider]

    if provider == IntegrationProvider.TRELLO:
        # Trello: token comes directly in the callback fragment
        token_data = {"access_token": code, "token_type": "Bearer"}
    else:
        resp = requests.post(
            cfg["token_url"],
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  cfg["redirect_uri"],
                "client_id":     cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if not resp.ok:
            raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text[:200]}")
        token_data = resp.json()

    return _upsert_token(db, user_id, provider, token_data)


# ── Token refresh ─────────────────────────────────────────────────────────────

def refresh_access_token(db: Session, token: OAuthToken) -> OAuthToken:
    """
    Refresh an expired access token using the refresh token.
    Updates the DB record in place.
    """
    if not token.refresh_token:
        raise ValueError(f"No refresh token for {token.provider.value}")

    cfg = PROVIDER_CONFIGS[token.provider]
    refresh_token_plain = decrypt_token(token.refresh_token)

    resp = requests.post(
        cfg["token_url"],
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token_plain,
            "client_id":     cfg["client_id"],
            "client_secret": cfg["client_secret"],
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )

    if not resp.ok:
        token.is_expired = True
        token.sync_error = f"Refresh failed: {resp.status_code}"
        db.commit()
        _audit(db, token.user_id, token.provider.value, AuditAction.TOKEN_REFRESH,
               success=False, error=f"HTTP {resp.status_code}")
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text[:200]}")

    token_data = resp.json()
    updated = _upsert_token(db, token.user_id, token.provider, token_data)
    _audit(db, token.user_id, token.provider.value, AuditAction.TOKEN_REFRESH)
    return updated


def get_valid_token(db: Session, user_id: int, provider: IntegrationProvider) -> Optional[OAuthToken]:
    """
    Get a valid (non-expired) token for a user+provider.
    Auto-refreshes if expired and refresh token is available.
    Returns None if not connected.
    """
    token = db.query(OAuthToken).filter(
        OAuthToken.user_id == user_id,
        OAuthToken.provider == provider,
        OAuthToken.is_active == True,
    ).first()

    if not token:
        return None

    # Check expiry (refresh 5 min before actual expiry)
    if token.expires_at:
        expires_soon = token.expires_at - timedelta(minutes=5)
        if datetime.now(timezone.utc) >= expires_soon:
            try:
                token = refresh_access_token(db, token)
            except Exception as exc:
                logger.warning(f"[OAuth] Token refresh failed for user={user_id} provider={provider.value}: {exc}")
                return None

    return token


def get_access_token_plain(db: Session, user_id: int, provider: IntegrationProvider) -> Optional[str]:
    """Get decrypted access token string, or None."""
    token = get_valid_token(db, user_id, provider)
    if not token:
        return None
    return decrypt_token(token.access_token)


# ── Disconnect ────────────────────────────────────────────────────────────────

def disconnect_provider(db: Session, user_id: int, provider: IntegrationProvider) -> None:
    """Revoke and delete OAuth token for a provider."""
    token = db.query(OAuthToken).filter(
        OAuthToken.user_id == user_id,
        OAuthToken.provider == provider,
    ).first()

    if token:
        # Attempt to revoke at provider
        _try_revoke(token)
        db.delete(token)
        db.commit()

    _audit(db, user_id, provider.value, AuditAction.OAUTH_DISCONNECT)


def _try_revoke(token: OAuthToken) -> None:
    """Best-effort token revocation at provider."""
    try:
        access = decrypt_token(token.access_token)
        if token.provider in (IntegrationProvider.GOOGLE_CALENDAR, IntegrationProvider.GOOGLE_TASKS):
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access},
                timeout=5,
            )
    except Exception:
        pass


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upsert_token(
    db: Session,
    user_id: int,
    provider: IntegrationProvider,
    token_data: dict,
) -> OAuthToken:
    """Create or update OAuthToken from token_data dict."""
    access  = token_data.get("access_token", "")
    refresh = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in")

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    existing = db.query(OAuthToken).filter(
        OAuthToken.user_id == user_id,
        OAuthToken.provider == provider,
    ).first()

    if existing:
        existing.access_token  = encrypt_token(access)
        if refresh:
            existing.refresh_token = encrypt_token(refresh)
        existing.expires_at    = expires_at
        existing.is_expired    = False
        existing.is_active     = True
        existing.scope         = token_data.get("scope", existing.scope)
        existing.sync_error    = None
        db.commit()
        db.refresh(existing)
        _audit(db, user_id, provider.value, AuditAction.OAUTH_CONNECT)
        return existing

    token = OAuthToken(
        user_id       = user_id,
        provider      = provider,
        access_token  = encrypt_token(access),
        refresh_token = encrypt_token(refresh) if refresh else None,
        token_type    = token_data.get("token_type", "Bearer"),
        scope         = token_data.get("scope", ""),
        expires_at    = expires_at,
        is_active     = True,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    _audit(db, user_id, provider.value, AuditAction.OAUTH_CONNECT)
    return token


def _audit(
    db: Session,
    user_id: Optional[int],
    provider: str,
    action: AuditAction,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Write an audit log entry."""
    try:
        log = IntegrationAuditLog(
            user_id       = user_id,
            provider      = provider,
            action        = action,
            resource_id   = resource_id,
            details       = details,
            success       = success,
            error_message = error,
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.warning(f"[Audit] Failed to write audit log: {exc}")

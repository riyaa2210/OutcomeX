"""
Security Routes
===============

Auth:
  POST /auth/refresh          — exchange refresh token for new access token
  POST /auth/logout           — revoke refresh token
  POST /auth/logout-all       — revoke all sessions

Files:
  GET  /files/signed          — serve a file via signed URL

Security dashboard (admin only):
  GET  /security/dashboard    — overview metrics
  GET  /security/audit-log    — paginated audit log
  GET  /security/anomalies    — recent anomaly events
  GET  /security/active-sessions — active refresh tokens
  DELETE /security/sessions/{user_id} — revoke all sessions for a user
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.auth import (
    get_current_user, verify_refresh_token, rotate_refresh_token,
    revoke_all_user_tokens, RefreshToken,
)
from backend.security.rbac import require_role, Role
from backend.security.audit_log import (
    SecurityAuditLog, AuditEventType, log_event, log_from_request,
)
from backend.security.file_security import verify_signed_url
from backend.security.anomaly_detector import check_and_alert

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Security"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )


# ── Token refresh ─────────────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/refresh")
def refresh_tokens(
    req: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    Old refresh token is revoked (rotation).
    """
    payload = verify_refresh_token(req.refresh_token, db)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload["user_id"]
    old_jti = payload["jti"]
    ip      = _get_ip(request)
    ua      = request.headers.get("user-agent", "")

    # Rotate refresh token
    new_refresh = rotate_refresh_token(old_jti, user_id, db, ip, ua)

    # Issue new access token
    from backend.app.auth import create_access_token
    new_access = create_access_token({"user_id": user_id})

    log_event(
        AuditEventType.TOKEN_REFRESH,
        user_id=user_id,
        ip_address=ip,
        user_agent=ua,
        details={"old_jti": old_jti},
    )

    return {
        "access_token":  new_access,
        "refresh_token": new_refresh,
        "token_type":    "bearer",
    }


@router.post("/auth/logout")
def logout(
    req: RefreshRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke the current refresh token (single device logout)."""
    payload = verify_refresh_token(req.refresh_token, db)
    if payload:
        jti = payload.get("jti")
        rt  = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
        if rt:
            rt.revoked = True
            db.commit()

    # Also revoke access token in Redis
    from backend.app.auth import verify_token
    from backend.security.anomaly_detector import revoke_token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_payload = verify_token(auth_header[7:])
        if access_payload and access_payload.get("jti"):
            revoke_token(access_payload["jti"], expires_in=900)

    log_from_request(request, AuditEventType.LOGOUT, user=current_user)
    return {"message": "Logged out successfully"}


@router.post("/auth/logout-all")
def logout_all(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke all refresh tokens for the current user (all devices)."""
    count = revoke_all_user_tokens(current_user.id, db)
    log_from_request(
        request, AuditEventType.LOGOUT, user=current_user,
        details={"sessions_revoked": count},
    )
    return {"message": f"Logged out from {count} session(s)"}


# ── Signed file access ────────────────────────────────────────────────────────

@router.get("/files/signed")
def serve_signed_file(
    path: str = Query(...),
    uid: int  = Query(...),
    exp: int  = Query(...),
    sig: str  = Query(...),
    current_user=Depends(get_current_user),
):
    """Serve a private file via signed URL."""
    if current_user.id != uid:
        raise HTTPException(status_code=403, detail="Signed URL user mismatch")

    if not verify_signed_url(path, uid, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired signed URL")

    full_path = Path(path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Prevent path traversal
    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
    try:
        full_path.resolve().relative_to(upload_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(full_path)


# ── Security dashboard (admin only) ──────────────────────────────────────────

@router.get("/security/dashboard")
def security_dashboard(
    hours: int = Query(24, ge=1, le=168),
    current_user=Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Security overview for admin dashboard."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    stats = db.execute(text("""
        SELECT
            COUNT(*)                                                    AS total_events,
            COUNT(CASE WHEN event_type = 'auth.login_success'  THEN 1 END) AS logins,
            COUNT(CASE WHEN event_type = 'auth.login_failed'   THEN 1 END) AS failed_logins,
            COUNT(CASE WHEN event_type = 'auth.register'       THEN 1 END) AS registrations,
            COUNT(CASE WHEN event_type = 'security.rate_limit' THEN 1 END) AS rate_limit_hits,
            COUNT(CASE WHEN event_type = 'security.rbac_denied' THEN 1 END) AS rbac_denials,
            COUNT(CASE WHEN event_type = 'security.anomaly'    THEN 1 END) AS anomalies,
            COUNT(CASE WHEN event_type = 'webhook.rejected'    THEN 1 END) AS webhook_rejections,
            COUNT(CASE WHEN event_type = 'security.file_rejected' THEN 1 END) AS file_rejections,
            COUNT(CASE WHEN NOT success                        THEN 1 END) AS total_failures,
            AVG(risk_score)                                             AS avg_risk_score,
            MAX(risk_score)                                             AS max_risk_score
        FROM security_audit_logs
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    # Top suspicious IPs
    top_ips = db.execute(text("""
        SELECT ip_address, COUNT(*) AS events,
               SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failures,
               MAX(risk_score) AS max_risk
        FROM security_audit_logs
        WHERE created_at >= :since AND ip_address IS NOT NULL
        GROUP BY ip_address
        ORDER BY failures DESC, events DESC
        LIMIT 10
    """), {"since": since}).fetchall()

    # Event type breakdown
    event_breakdown = db.execute(text("""
        SELECT event_type, COUNT(*) AS cnt
        FROM security_audit_logs
        WHERE created_at >= :since
        GROUP BY event_type
        ORDER BY cnt DESC
        LIMIT 20
    """), {"since": since}).fetchall()

    # Hourly trend
    trend = db.execute(text("""
        SELECT DATE_TRUNC('hour', created_at) AS hour,
               COUNT(*) AS events,
               COUNT(CASE WHEN NOT success THEN 1 END) AS failures
        FROM security_audit_logs
        WHERE created_at >= :since
        GROUP BY hour
        ORDER BY hour ASC
    """), {"since": since}).fetchall()

    def _f(v): return round(float(v), 2) if v is not None else 0
    def _i(v): return int(v) if v is not None else 0

    return {
        "period_hours": hours,
        "summary": {
            "total_events":       _i(stats.total_events),
            "logins":             _i(stats.logins),
            "failed_logins":      _i(stats.failed_logins),
            "registrations":      _i(stats.registrations),
            "rate_limit_hits":    _i(stats.rate_limit_hits),
            "rbac_denials":       _i(stats.rbac_denials),
            "anomalies":          _i(stats.anomalies),
            "webhook_rejections": _i(stats.webhook_rejections),
            "file_rejections":    _i(stats.file_rejections),
            "total_failures":     _i(stats.total_failures),
            "avg_risk_score":     _f(stats.avg_risk_score),
            "max_risk_score":     _i(stats.max_risk_score),
        },
        "top_suspicious_ips": [
            {
                "ip":       row.ip_address,
                "events":   int(row.events),
                "failures": int(row.failures),
                "max_risk": int(row.max_risk),
            }
            for row in top_ips
        ],
        "event_breakdown": [
            {"event_type": row.event_type, "count": int(row.cnt)}
            for row in event_breakdown
        ],
        "hourly_trend": [
            {
                "hour":     row.hour.isoformat() if row.hour else "",
                "events":   int(row.events),
                "failures": int(row.failures),
            }
            for row in trend
        ],
    }


@router.get("/security/audit-log")
def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    ip_address: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    current_user=Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Paginated security audit log."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(SecurityAuditLog).filter(SecurityAuditLog.created_at >= since)

    if event_type:
        q = q.filter(SecurityAuditLog.event_type == event_type)
    if user_id:
        q = q.filter(SecurityAuditLog.user_id == user_id)
    if ip_address:
        q = q.filter(SecurityAuditLog.ip_address == ip_address)
    if success is not None:
        q = q.filter(SecurityAuditLog.success == success)

    total = q.count()
    logs  = q.order_by(SecurityAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "logs": [
            {
                "id":            l.id,
                "event_type":    l.event_type,
                "user_id":       l.user_id,
                "user_email":    l.user_email,
                "user_role":     l.user_role,
                "ip_address":    l.ip_address,
                "endpoint":      l.endpoint,
                "method":        l.method,
                "resource_type": l.resource_type,
                "resource_id":   l.resource_id,
                "details":       l.details,
                "success":       l.success,
                "risk_score":    l.risk_score,
                "created_at":    l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.get("/security/anomalies")
def get_anomalies(
    hours: int = Query(24, ge=1, le=168),
    current_user=Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Recent anomaly and high-risk events."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs  = db.query(SecurityAuditLog).filter(
        SecurityAuditLog.created_at >= since,
        SecurityAuditLog.risk_score >= 50,
    ).order_by(SecurityAuditLog.risk_score.desc()).limit(50).all()

    return {
        "count": len(logs),
        "anomalies": [
            {
                "id":         l.id,
                "event_type": l.event_type,
                "user_id":    l.user_id,
                "ip_address": l.ip_address,
                "risk_score": l.risk_score,
                "details":    l.details,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.get("/security/active-sessions")
def get_active_sessions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active refresh token sessions for the current user."""
    sessions = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > datetime.now(timezone.utc),
    ).order_by(RefreshToken.created_at.desc()).all()

    return {
        "count": len(sessions),
        "sessions": [
            {
                "id":         s.id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sessions
        ],
    }


@router.delete("/security/sessions/{target_user_id}")
def revoke_user_sessions(
    target_user_id: int,
    current_user=Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Admin: revoke all sessions for a user."""
    count = revoke_all_user_tokens(target_user_id, db)
    log_event(
        AuditEventType.TOKEN_REVOKED,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(target_user_id),
        details={"sessions_revoked": count},
    )
    return {"revoked": count}

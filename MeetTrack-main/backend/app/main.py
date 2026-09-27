# ✅ MUST BE FIRST LINES (TOP OF FILE)
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.app.database import Base, engine, SessionLocal
from backend.app.settings import CORS_ORIGINS
from fastapi.middleware.cors import CORSMiddleware

# Import models (important)
from backend.models import user, meeting, action_item, result, webhook_log
from backend.models.task_log import TaskLog
from backend.models.user import User
# LLM metrics table — must be imported before create_all
from backend.services.llm.metrics import LLMCallLog  # noqa: F401
# Evaluation tables — must be imported before create_all
from backend.models.evaluation import EvalResult, HumanFeedback, BenchmarkSample  # noqa: F401
# Integration tables
from backend.models.integration import OAuthToken, IntegrationAuditLog, ExternalMeeting  # noqa: F401
# Security tables
from backend.app.auth import RefreshToken  # noqa: F401
from backend.security.audit_log import SecurityAuditLog  # noqa: F401

# Routes
from backend.routes.upload_routes import router as upload_router
from backend.routes.process_routes import router as process_router
from backend.routes.result_routes import router as result_router
from backend.routes.action_item_routes import router as action_router
from backend.routes.meeting_routes import router as meeting_router
from backend.routes.task_routes import router as task_router
from backend.routes.webhook_routes import router as webhook_router
from backend.routes.rag_routes import router as rag_router
from backend.routes.live_routes import router as live_router
from backend.routes.analytics_routes import router as analytics_router
from backend.routes.task_status_routes import router as task_status_router
from backend.routes.llm_admin_routes import router as llm_admin_router
from backend.routes.eval_routes import router as eval_router
from backend.routes.integration_routes import router as integration_router
from backend.routes.security_routes import router as security_router

# Schemas & CRUD
from backend.app import schemas, crud
from backend.app.auth import create_access_token, get_current_user

# Create tables — use checkfirst to skip existing tables/indexes
try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"DB create_all warning (non-fatal): {_e}")

app = FastAPI(title="MeetTrack API", version="1.0.0")

# ✅ CORS — reads allowed origins from env (comma-separated)
# If CORS_ORIGINS is not set, allow all origins (safe fallback for initial deploy)
_raw_origins = os.getenv("CORS_ORIGINS", "*")

if _raw_origins.strip() == "*":
    ALLOWED_ORIGINS = ["*"]
else:
    ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_ORIGINS != ["*"],  # credentials not allowed with wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security headers middleware ───────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # XSS protection
        response.headers["X-Content-Type-Options"]    = "nosniff"
        response.headers["X-Frame-Options"]           = "DENY"
        response.headers["X-XSS-Protection"]          = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "camera=(), microphone=(), geolocation=()"
        # CSP — allow same-origin + trusted CDNs only
        response.headers["Content-Security-Policy"]   = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' wss: https:;"
        )
        # Remove server fingerprint
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        # Track 404s for anomaly detection
        if response.status_code == 404:
            try:
                from backend.security.anomaly_detector import record_404
                ip = request.client.host if request.client else "unknown"
                record_404(ip)
            except Exception:
                pass  # never let anomaly detection crash a real response

        return response

app.add_middleware(SecurityHeadersMiddleware)

# ✅ DB Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ✅ Root
@app.get("/")
def root():
    return {"message": "Automated Meeting Outcome Tracker running"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint for Docker/load balancer probes.
    Verifies DB connectivity and returns service status.
    """
    import time
    start = time.perf_counter()
    db_ok = False
    db_error = None

    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    latency_ms = round((time.perf_counter() - start) * 1000, 1)

    status = "healthy" if db_ok else "degraded"
    return {
        "status":     status,
        "service":    "outcomex-backend",
        "version":    "1.0.0",
        "db":         "ok" if db_ok else f"error: {db_error}",
        "latency_ms": latency_ms,
    }


@app.get("/debug/config")
def debug_config():
    """Check env vars are set correctly on Render (remove after debugging)"""
    colab_url = os.getenv("COLAB_API_URL", "") or os.getenv("COLAB_WHISPER_URL", "")
    return {
        "COLAB_API_URL_set": bool(os.getenv("COLAB_API_URL")),
        "COLAB_WHISPER_URL_set": bool(os.getenv("COLAB_WHISPER_URL")),
        "colab_url_preview": colab_url[:40] + "..." if len(colab_url) > 40 else colab_url,
        "CORS_ORIGINS": os.getenv("CORS_ORIGINS", "not set"),
    }


# ✅ Get all meetings for current user
@app.get("/meetings")
def get_all_meetings(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    from backend.models.meeting import Meeting
    meetings = db.query(Meeting).filter(Meeting.user_id == current_user.id).all()
    return [
        {
            "id": m.id,
            "title": m.title,
            "audio_path": m.audio_path,
            "created_at": m.created_at
        }
        for m in meetings
    ]


# ✅ REGISTER
@app.post("/register", response_model=schemas.UserResponse)
def register(
    user: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    from backend.security.audit_log import log_from_request, AuditEventType

    db_user = crud.create_user(db, user)
    if not db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        log_from_request(request, AuditEventType.REGISTER, user=db_user)
    except Exception:
        pass
    return db_user


# ✅ LOGIN
@app.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    from backend.security.audit_log import log_from_request, AuditEventType
    from backend.app.auth import create_refresh_token

    db_user = crud.login_user(
        db,
        schemas.UserLogin(email=form_data.username, password=form_data.password)
    )

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token  = create_access_token(data={"user_id": db_user.id})
    refresh_token = create_refresh_token(
        db_user.id, db,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )

    try:
        log_from_request(request, AuditEventType.LOGIN_SUCCESS, user=db_user)
    except Exception:
        pass

    import json
    skills = json.loads(db_user.skills) if db_user.skills else []

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        "user_id":       db_user.id,
        "email":         db_user.email,
        "full_name":     db_user.full_name,
        "role":          db_user.role,
        "phone_number":  db_user.phone_number,
        "profile_image": db_user.profile_image,
        "bio":           db_user.bio,
        "job_title":     db_user.job_title,
        "department":    db_user.department,
        "employee_id":   db_user.employee_id,
        "manager_name":  db_user.manager_name,
        "skills":        skills,
        "location":      db_user.location,
        "work_mode":     db_user.work_mode,
        "timezone":      db_user.timezone,
    }


# ✅ GET PROFILE (Fetch full user profile)
@app.get("/profile/{user_id}", response_model=schemas.UserResponse)
def get_profile(
    user_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Ensure user can only view their own profile
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's profile")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


# ✅ UPDATE PROFILE
@app.put("/profile/{user_id}", response_model=schemas.UserResponse)
def update_profile(
    user_id: int,
    user_data: schemas.UserUpdate,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from backend.security.rbac import assert_owns_or_admin
    from backend.security.audit_log import log_from_request, AuditEventType
    assert_owns_or_admin(user_id, current_user)

    updated_user = crud.update_user_profile(db, user_id, user_data)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    log_from_request(request, AuditEventType.PROFILE_UPDATED, user=current_user,
                     resource_type="user", resource_id=str(user_id))
    return updated_user


# ✅ UPLOAD PROFILE IMAGE
@app.post("/profile/{user_id}/upload-image")
async def upload_profile_image(
    user_id: int,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and save profile image with security validation."""
    import shutil
    import uuid
    from pathlib import Path
    from backend.security.rbac import assert_owns_or_admin
    from backend.security.file_security import validate_upload, ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_SIZE

    assert_owns_or_admin(user_id, current_user)

    # Validate file (extension, MIME, size, malware scan)
    meta = await validate_upload(file, allowed_extensions=ALLOWED_IMAGE_EXTENSIONS, max_size=MAX_IMAGE_SIZE)

    upload_dir = Path("uploads/profile_images")
    upload_dir.mkdir(parents=True, exist_ok=True)

    unique_filename = f"user_{user_id}_{uuid.uuid4().hex}{meta['extension']}"
    file_path = upload_dir / unique_filename

    try:
        content = await file.read()
        with open(file_path, "wb") as buf:
            buf.write(content)

        relative_path = str(file_path).replace("\\", "/")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.profile_image = relative_path
        db.commit()
        db.refresh(user)

        return {"status": "success", "message": "Image uploaded successfully", "file_path": relative_path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")


# ✅ GET PROFILE IMAGE (for serving images)
@app.get("/profile/{user_id}/image")
def get_profile_image(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get profile image path for a user"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.profile_image:
        raise HTTPException(status_code=404, detail="No profile image found")
    
    return {"profile_image": user.profile_image}


@app.get("/results/pending/tasks")
def get_pending_tasks(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return real pending action items for the current user."""
    from backend.models.action_item import ActionItem
    from backend.models.meeting import Meeting
    items = (
        db.query(ActionItem)
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .filter(Meeting.user_id == current_user.id, ActionItem.status == "Pending")
        .order_by(ActionItem.deadline.asc().nullslast())
        .limit(20)
        .all()
    )
    return [
        {
            "id":        item.id,
            "assignee":  item.assigned_to,
            "task":      item.title or item.description,
            "deadline":  str(item.deadline) if item.deadline else None,
            "status":    item.status,
            "meeting_id": item.meeting_id,
        }
        for item in items
    ]


# ✅ CONTACT form — stores/logs contact messages
@app.post("/contact")
def contact(
    payload: dict,
    request: Request,
):
    """Accept contact form submissions and log them server-side."""
    import logging as _log
    _logger = _log.getLogger("contact")
    full_name = str(payload.get("full_name", "")).strip()[:120]
    email     = str(payload.get("email",     "")).strip()[:254]
    message   = str(payload.get("message",   "")).strip()[:2000]

    if not full_name or not email or not message:
        raise HTTPException(status_code=422, detail="full_name, email, and message are required")

    _logger.info(f"[Contact] From: {full_name} <{email}> | {message[:80]}")
    return {"message": "Thanks for reaching out! We'll get back to you soon."}



app.include_router(upload_router)
app.include_router(process_router)
app.include_router(result_router)
app.include_router(action_router)
app.include_router(meeting_router)
app.include_router(task_router)
app.include_router(webhook_router)
app.include_router(rag_router)
app.include_router(live_router)
app.include_router(analytics_router)
app.include_router(task_status_router)
app.include_router(llm_admin_router)
app.include_router(eval_router)
app.include_router(integration_router)
app.include_router(security_router)

"""
Authentication — JWT Access + Refresh Token Flow
=================================================
Access token:  15 min (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)
Refresh token: 7 days (configurable via REFRESH_TOKEN_EXPIRE_DAYS)

Token types distinguished by "type" claim:
  access  → used for API calls
  refresh → used only at POST /auth/refresh

Refresh tokens are stored in DB (RefreshToken table) for:
  - Revocation on logout
  - Rotation (each refresh issues a new refresh token)
  - Replay detection

Passwords hashed with bcrypt (passlib).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.app.database import Base, SessionLocal
from backend.app.settings import SECRET_KEY, ALGORITHM

# ── Config ────────────────────────────────────────────────────────────────────

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",   "7"))

# ── Password hashing ──────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    # Support legacy plaintext passwords during migration
    if not hashed.startswith("$2b$") and not hashed.startswith("$2a$"):
        return plain == hashed  # legacy comparison
    return pwd_context.verify(plain, hashed)


# ── Refresh token DB model ────────────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_token_jti",     "jti",     unique=True),
        Index("ix_refresh_token_user_id", "user_id"),
        {"extend_existing": True},
    )

    id         = Column(Integer, primary_key=True)
    jti        = Column(String(64), unique=True, nullable=False)  # JWT ID
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revoked    = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)


# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire    = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "type": "access", "jti": jti})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: int,
    db: Session,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Create a refresh token and persist it to DB."""
    jti        = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "user_id": user_id,
        "type":    "refresh",
        "jti":     jti,
        "exp":     expires_at,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # Persist
    rt = RefreshToken(
        jti        = jti,
        user_id    = user_id,
        expires_at = expires_at,
        ip_address = ip_address,
        user_agent = (user_agent or "")[:500],
    )
    db.add(rt)
    db.commit()

    return token


def rotate_refresh_token(
    old_jti: str,
    user_id: int,
    db: Session,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Revoke old refresh token and issue a new one (rotation)."""
    old = db.query(RefreshToken).filter(RefreshToken.jti == old_jti).first()
    if old:
        old.revoked = True
        db.commit()

    return create_refresh_token(user_id, db, ip_address, user_agent)


# ── Token verification ────────────────────────────────────────────────────────

def verify_token(token: str, expected_type: str = "access") -> Optional[dict]:
    """Decode and validate a JWT. Returns payload or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            return None

        # Check revocation for access tokens
        if expected_type == "access":
            from backend.security.anomaly_detector import is_token_revoked
            jti = payload.get("jti", "")
            if jti and is_token_revoked(jti):
                return None

        return payload
    except JWTError:
        return None


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}")


def verify_refresh_token(token: str, db: Session) -> Optional[dict]:
    """Verify a refresh token against DB (checks revocation)."""
    payload = verify_token(token, expected_type="refresh")
    if not payload:
        return None

    jti = payload.get("jti")
    rt  = db.query(RefreshToken).filter(
        RefreshToken.jti     == jti,
        RefreshToken.revoked == False,
    ).first()

    if not rt:
        return None

    if rt.expires_at < datetime.now(timezone.utc):
        rt.revoked = True
        db.commit()
        return None

    return payload


def revoke_all_user_tokens(user_id: int, db: Session) -> int:
    """Revoke all refresh tokens for a user (logout all devices)."""
    count = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()
    return count


# ── FastAPI dependencies ──────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token, expected_type="access")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    db = SessionLocal()
    try:
        from backend.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def get_optional_user(token: Optional[str] = Depends(oauth2_scheme)):
    """Like get_current_user but returns None instead of raising."""
    try:
        return get_current_user(token)
    except HTTPException:
        return None

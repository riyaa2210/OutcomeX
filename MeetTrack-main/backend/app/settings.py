import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file (2 levels up from this file)
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/meettrack"
)

# ── AWS ───────────────────────────────────────────────────────────────────────
AWS_REGION        = os.getenv("AWS_REGION", "ap-south-1")
# Use the standard AWS env var names (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
AWS_ACCESS_KEY    = os.getenv("AWS_ACCESS_KEY_ID")      # standard name
AWS_SECRET_KEY    = os.getenv("AWS_SECRET_ACCESS_KEY")  # standard name
TRANSCRIBE_BUCKET = os.getenv("TRANSCRIBE_BUCKET")
TRANSCRIBE_ROLE_ARN = os.getenv("TRANSCRIBE_ROLE_ARN")

# ── AI ────────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── Authentication ────────────────────────────────────────────────────────────
SECRET_KEY    = os.getenv("SECRET_KEY", "change-me-generate-with-secrets-token-hex-32")
ALGORITHM     = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",   "7"))

# ── CORS ──────────────────────────────────────────────────────────────────────
# Read from env (comma-separated). Falls back to localhost dev origins.
_raw_cors = os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173"
)
CORS_ORIGINS: list[str] = (
    ["*"]
    if _raw_cors.strip() == "*"
    else [o.strip() for o in _raw_cors.split(",") if o.strip()]
)

# ── Upload ────────────────────────────────────────────────────────────────────
UPLOAD_DIR       = "uploads"
MAX_UPLOAD_SIZE  = 100 * 1024 * 1024  # 100 MB

# ── Redis / Celery ────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Local Whisper (faster-whisper) ────────────────────────────────────────────
# Set USE_LOCAL_WHISPER=true to use local faster-whisper instead of Colab
USE_LOCAL_WHISPER  = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny/base/small/medium

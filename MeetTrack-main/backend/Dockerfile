# ── Backend Dockerfile ────────────────────────────────────────────────────────
# Multi-stage build: builder → runtime
# Final image: python:3.11-slim (~200 MB vs ~1 GB full)

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for psycopg2, cryptography, spacy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps into a prefix dir (keeps runtime image clean)
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm --target /install/lib/python3.11/site-packages

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="OutcomeX Team"
LABEL org.opencontainers.image.title="outcomex-backend"
LABEL org.opencontainers.image.description="OutcomeX FastAPI backend"

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy application code
COPY . .

# Create uploads directory with correct permissions
RUN mkdir -p /app/uploads/profile_images \
    && chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

EXPOSE 8000

# Entrypoint: use exec form for proper signal handling
CMD ["uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log"]

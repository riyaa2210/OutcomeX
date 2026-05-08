"""
Pytest configuration and shared fixtures.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Test DB ───────────────────────────────────────────────────────────────────

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test_outcomex",
)

# Set env vars before importing app
os.environ.setdefault("DATABASE_URL",  TEST_DATABASE_URL)
os.environ.setdefault("SECRET_KEY",    "test-secret-key-not-for-production")
os.environ.setdefault("REDIS_URL",     "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT",   "test")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL)
    # Enable pgvector
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_client(db_engine):
    """FastAPI test client with real DB."""
    from backend.app.database import Base
    Base.metadata.create_all(bind=db_engine)

    from backend.app.main import app
    from backend.app.database import SessionLocal

    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers(app_client):
    """Register + login a test user, return auth headers."""
    import uuid
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"

    # Register
    app_client.post("/register", json={
        "full_name": "Test User",
        "email":     email,
        "password":  "TestPass123!",
    })

    # Login
    resp = app_client.post("/login", data={
        "username": email,
        "password": "TestPass123!",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

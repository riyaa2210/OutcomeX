"""
API Smoke Tests
===============
Run against a live backend (local or deployed).
Used in CI after Docker build to verify the deployment is healthy.

Set API_BASE_URL env var to target a specific environment.
"""

import os
import pytest
import httpx

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def auth_token(client):
    """Register + login a smoke test user."""
    import uuid
    email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"

    client.post("/register", json={
        "full_name": "Smoke Test",
        "email":     email,
        "password":  "SmokePass123!",
    })

    resp = client.post("/login", data={
        "username": email,
        "password": "SmokePass123!",
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── Health ────────────────────────────────────────────────────────────────────

def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "message" in resp.json()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "db" in data
    assert "latency_ms" in data


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_register_and_login(client):
    import uuid
    email = f"reg_{uuid.uuid4().hex[:8]}@example.com"

    reg = client.post("/register", json={
        "full_name": "Reg User",
        "email":     email,
        "password":  "RegPass123!",
    })
    assert reg.status_code == 200

    login = client.post("/login", data={
        "username": email,
        "password": "RegPass123!",
    })
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_login_wrong_password(client):
    resp = client.post("/login", data={
        "username": "nobody@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


# ── Protected endpoints ───────────────────────────────────────────────────────

def test_meetings_requires_auth(client):
    resp = client.get("/meetings")
    assert resp.status_code == 401


def test_meetings_with_auth(client, auth_token):
    resp = client.get("/meetings", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_overview(client, auth_token):
    resp = client.get(
        "/analytics/overview?days=7",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_meetings" in data


def test_eval_dashboard(client, auth_token):
    resp = client.get(
        "/eval/dashboard?hours=24",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200


def test_integrations_list(client, auth_token):
    resp = client.get(
        "/integrations",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "integrations" in data


def test_llm_status(client, auth_token):
    resp = client.get(
        "/llm/status",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data


def test_task_dashboard(client, auth_token):
    resp = client.get(
        "/tasks/dashboard/overview?hours=24",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200

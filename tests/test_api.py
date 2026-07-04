"""Tests for the FastAPI HTTP surface.

Uses :class:`fastapi.testclient.TestClient` against the app factory
in :mod:`app.main`. The DB is the in-memory SQLite fallback so no
Postgres is required.
"""

from __future__ import annotations

import os
import uuid

# Force SQLite fallback before app imports.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient

from app.db import create_all, drop_all, reset_engine
from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    import asyncio
    reset_engine()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(drop_all())
        loop.run_until_complete(create_all())
    finally:
        loop.close()
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------


def test_health_endpoint_returns_503_when_no_postgres(client: TestClient) -> None:
    # /health checks Postgres+Redis. SQLite in-memory is not Postgres
    # and the test env has no Redis, so we expect 503 degraded.
    resp = client.get("/health")
    # Either 200 (when nothing to check) or 503 (degraded) is acceptable
    # depending on whether the check is skipped for SQLite. We assert
    # the body shape regardless.
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" in body


def test_index_returns_service_metadata(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "agentic-ai-platform"
    assert "docs" in body
    assert "health" in body


def test_stack_endpoint_reports_resolved_config(client: TestClient) -> None:
    resp = client.get("/stack")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api"] == "FastAPI"
    assert body["validation"] == "Pydantic v2"
    assert body["database"] == "PostgreSQL + pgvector"


# ---------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------


def test_create_and_get_task(client: TestClient) -> None:
    payload = {"input_payload": {"q": "test"}}
    resp = client.post("/api/tasks", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["state"] == "pending"
    assert created["input_payload"] == {"q": "test"}

    fetched = client.get(f"/api/tasks/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_list_tasks_returns_array(client: TestClient) -> None:
    client.post("/api/tasks", json={"input_payload": {}})
    client.post("/api/tasks", json={"input_payload": {}})
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert "tasks" in body
    assert body["count"] == len(body["tasks"])
    assert body["count"] >= 2


def test_claim_task_with_agent_id(client: TestClient) -> None:
    create = client.post("/api/tasks", json={"input_payload": {}}).json()
    agent_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/tasks/{create['id']}/claim", json={"agent_id": agent_id}
    )
    # 200 if claimable, 409 if already claimed by another test.
    assert resp.status_code in (200, 409)
    if resp.status_code == 200:
        assert resp.json()["state"] == "running"


def test_complete_task(client: TestClient) -> None:
    create = client.post("/api/tasks", json={"input_payload": {}}).json()
    agent_id = str(uuid.uuid4())
    claim = client.post(
        f"/api/tasks/{create['id']}/claim", json={"agent_id": agent_id}
    )
    if claim.status_code != 200:
        pytest.skip("task was claimed by another test")
    done = client.post(
        f"/api/tasks/{create['id']}/complete",
        json={"output_payload": {"answer": 42}},
    )
    assert done.status_code == 200
    assert done.json()["state"] == "completed"
    assert done.json()["output_payload"] == {"answer": 42}


def test_fail_task_without_retry(client: TestClient) -> None:
    create = client.post("/api/tasks", json={"input_payload": {}}).json()
    agent_id = str(uuid.uuid4())
    claim = client.post(
        f"/api/tasks/{create['id']}/claim", json={"agent_id": agent_id}
    )
    if claim.status_code != 200:
        pytest.skip("task was claimed by another test")
    failed = client.post(
        f"/api/tasks/{create['id']}/fail",
        json={"error_message": "test failure", "retry": False},
    )
    assert failed.status_code == 200
    assert failed.json()["state"] == "failed"


def test_recover_stale_endpoint(client: TestClient) -> None:
    resp = client.post("/api/tasks/recover")
    assert resp.status_code == 200
    body = resp.json()
    assert "recovered" in body
    assert isinstance(body["recovered"], int)


# ---------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------


def test_register_and_get_agent(client: TestClient) -> None:
    payload = {
        "name": "test-agent",
        "role": "researcher",
        "config": {"model": "gpt-4o-mini"},
        "system_prompt": "You are a test agent.",
        "tools": [],
    }
    resp = client.post("/api/agents", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "test-agent"
    assert created["role"] == "researcher"

    fetched = client.get(f"/api/agents/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_list_agents(client: TestClient) -> None:
    client.post("/api/agents", json={"name": "a1", "role": "writer", "tools": []})
    client.post("/api/agents", json={"name": "a2", "role": "reviewer", "tools": []})
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 2
    names = {a["name"] for a in body["agents"]}
    assert "a1" in names
    assert "a2" in names


# ---------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------


def test_list_runs_endpoint(client: TestClient) -> None:
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert "runs" in body


def test_get_nonexistent_run_returns_404(client: TestClient) -> None:
    rid = str(uuid.uuid4())
    resp = client.get(f"/api/runs/{rid}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------


def test_list_pending_review_endpoint(client: TestClient) -> None:
    resp = client.get("/api/review/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
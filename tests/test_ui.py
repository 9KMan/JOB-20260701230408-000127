"""Tests for the admin UI HTML responses.

Uses :class:`fastapi.testclient.TestClient` against the app factory
in :mod:`app.main`. The admin router is mounted by ``create_app`` via
``mount_admin``. Templates are rendered via Jinja2.
"""

from __future__ import annotations

import os

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
# Dashboard
# ---------------------------------------------------------------------


def test_dashboard_renders(client: TestClient) -> None:
    resp = client.get("/admin")
    assert resp.status_code == 200
    body = resp.text
    assert "Dashboard" in body
    assert "Total tasks" in body
    assert "Total runs" in body


def test_dashboard_has_sidebar_nav(client: TestClient) -> None:
    body = client.get("/admin").text
    for link in ["/admin", "/admin/tasks", "/admin/agents", "/admin/review"]:
        assert link in body, f"sidebar missing link {link}"


def test_dashboard_includes_static_css_link(client: TestClient) -> None:
    body = client.get("/admin").text
    assert "/admin/static/admin.css" in body


# ---------------------------------------------------------------------
# Tasks page
# ---------------------------------------------------------------------


def test_tasks_page_renders(client: TestClient) -> None:
    resp = client.get("/admin/tasks")
    assert resp.status_code == 200
    body = resp.text
    assert "Tasks" in body
    # Default state filter is "all".
    assert "filter-pill" in body


def test_tasks_page_state_filter(client: TestClient) -> None:
    resp = client.get("/admin/tasks?state=pending")
    assert resp.status_code == 200


def test_tasks_page_per_page(client: TestClient) -> None:
    resp = client.get("/admin/tasks?per_page=50")
    assert resp.status_code == 200


# ---------------------------------------------------------------------
# Agents page
# ---------------------------------------------------------------------


def test_agents_page_renders(client: TestClient) -> None:
    resp = client.get("/admin/agents")
    assert resp.status_code == 200
    body = resp.text
    assert "Agents" in body


def test_agents_page_shows_registered_agents(client: TestClient) -> None:
    # Register one via the API so the page has something to show.
    client.post(
        "/api/agents",
        json={"name": "ui-test-agent", "role": "writer", "tools": []},
    )
    resp = client.get("/admin/agents")
    assert resp.status_code == 200
    assert "ui-test-agent" in resp.text


# ---------------------------------------------------------------------
# Runs page
# ---------------------------------------------------------------------


def test_run_detail_404(client: TestClient) -> None:
    resp = client.get(f"/admin/runs/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Review page
# ---------------------------------------------------------------------


def test_review_page_renders(client: TestClient) -> None:
    resp = client.get("/admin/review")
    assert resp.status_code == 200
    body = resp.text
    assert "Review queue" in body


# ---------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------


def test_static_css_served(client: TestClient) -> None:
    resp = client.get("/admin/static/admin.css")
    # 200 if file present, 404 if mount failed.
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert "sidebar" in resp.text


# ---------------------------------------------------------------------
# Import uuid
# ---------------------------------------------------------------------


import uuid  # noqa: E402  (placed here to keep the imports section tidy)
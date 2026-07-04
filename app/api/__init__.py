"""HTTP API package — FastAPI routers for tasks, agents, runs, and review.

This package owns the HTTP surface of the platform. The four sub-routers
each own one resource family:

* :mod:`app.api.tasks` — :class:`TaskQueue` enqueue/claim/complete/fail + list.
* :mod:`app.api.agents` — agent CRUD + ad-hoc ``run`` endpoint.
* :mod:`app.api.runs` — read-only run audit endpoints.
* :mod:`app.api.review` — HITL review queue endpoints.

The :func:`mount_routers` helper wires them onto a :class:`fastapi.FastAPI`
app instance under the ``/api`` prefix. ``app.main.create_app`` calls it
during app construction.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.api.agents import router as agents_router
from app.api.review import router as review_router
from app.api.runs import router as runs_router
from app.api.tasks import router as tasks_router

__all__ = [
    "api_router",
    "mount_routers",
]


# A standalone composite router for tests / apps that prefer
# `app.include_router(api_router)` over `mount_routers(app)`.
api_router = APIRouter(prefix="/api")
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(runs_router, prefix="/runs", tags=["runs"])
api_router.include_router(review_router, prefix="/review", tags=["review"])


def mount_routers(app: FastAPI) -> None:
    """Mount the four resource routers under ``/api``.

    Idempotent — calling twice produces the same set of routes
    (FastAPI dedupes by path). Safe to call from a FastAPI app factory.
    """
    app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
    app.include_router(runs_router, prefix="/api/runs", tags=["runs"])
    app.include_router(review_router, prefix="/api/review", tags=["review"])
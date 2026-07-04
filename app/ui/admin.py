"""Admin router — server-side rendered HTML pages.

Mounts at ``/admin`` by :func:`app.ui.admin.mount_admin` (which
``app.main.create_app`` calls during app construction).

Pages:

* ``/admin``              — dashboard with task/run counts and recent activity.
* ``/admin/tasks``        — paginated task list with state filter.
* ``/admin/agents``       — agent list with role badges.
* ``/admin/runs/{run_id}`` — single-run detail with timeline.
* ``/admin/review``       — review queue with one-click approve/reject.

The page templates live in :data:`ADMIN_TEMPLATE_DIR`; static assets
(CSS) live in :data:`STATIC_DIR`.

All data is fetched via a fresh ``session_scope()`` per request. We
do *not* cache — these pages are operator-only and rendered rarely.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.db import session_scope
from app.models import Agent, Run, Task, TaskState
from app.orchestrator.review import (
    HumanReviewQueue,
    get_default_review_queue,
    reset_default_review_queue,
)

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

UI_DIR = Path(__file__).resolve().parent
ADMIN_TEMPLATE_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"

templates = Jinja2Templates(directory=str(ADMIN_TEMPLATE_DIR))

# ---------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------

router = APIRouter(prefix="/admin", tags=["admin"])


def mount_admin(app: Any) -> None:
    """Mount the admin router + static files onto a FastAPI app.

    Idempotent — calling twice produces the same set of routes.
    """
    app.include_router(router)
    if STATIC_DIR.exists():
        app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin-static")


# ---------------------------------------------------------------------
# Async DB helpers (sync wrappers for the templates)
# ---------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run an async coroutine from sync route handlers.

    FastAPI accepts ``async def`` handlers directly, but we keep these
    handlers sync because the templates render a small, fixed number
    of records and there's no win in the async path here.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _dashboard_data() -> dict[str, Any]:
    async with session_scope() as session:
        # Per-state task counts
        state_counts = dict(
            (await session.execute(
                select(Task.state, func.count())
                .group_by(Task.state)
            )).all()
        )
        total_tasks = sum(state_counts.values())
        total_runs = (await session.execute(select(func.count(Run.id)))).scalar_one()
        total_agents = (await session.execute(select(func.count(Agent.id)))).scalar_one()
        # Recent runs for activity list
        recent_runs_q = select(Run).order_by(Run.started_at.desc().nullslast()).limit(10)
        recent_runs = (await session.execute(recent_runs_q)).scalars().all()
        # Recent tasks
        recent_tasks_q = select(Task).order_by(Task.created_at.desc()).limit(10)
        recent_tasks = (await session.execute(recent_tasks_q)).scalars().all()
    return {
        "total_tasks": total_tasks,
        "total_runs": total_runs,
        "total_agents": total_agents,
        "state_counts": {s: state_counts.get(s.value, 0) for s in TaskState},
        "recent_runs": [_serialize_run(r) for r in recent_runs],
        "recent_tasks": [_serialize_task(r) for r in recent_tasks],
    }


async def _tasks_data(state: Optional[str], page: int, per_page: int) -> dict[str, Any]:
    offset = max(0, (page - 1) * per_page)
    async with session_scope() as session:
        stmt = select(Task).order_by(Task.created_at.desc())
        if state:
            try:
                stmt = stmt.where(Task.state == TaskState(state).value)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown state: {state}",
                )
        total = (await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await session.execute(stmt.limit(per_page).offset(offset))).scalars().all()
    return {
        "state": state or "all",
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "tasks": [_serialize_task(r) for r in rows],
    }


async def _agents_data() -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (await session.execute(
            select(Agent).order_by(Agent.created_at.desc())
        )).scalars().all()
    return [_serialize_agent(r) for r in rows]


async def _run_detail(run_id: uuid.UUID) -> Optional[dict[str, Any]]:
    async with session_scope() as session:
        row = await session.get(Run, run_id)
        if row is None:
            return None
    return _serialize_run(row, include_log=True)


async def _review_data() -> list[dict[str, Any]]:
    queue = get_default_review_queue()
    pending = await queue.list_pending(limit=200)
    return [_serialize_review(item) for item in pending]


# ---------------------------------------------------------------------
# Serialization helpers (used by templates)
# ---------------------------------------------------------------------


def _serialize_task(t: Task) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "state": t.state,
        "input_payload": t.input_payload or {},
        "output_payload": t.output_payload or {},
        "assigned_agent_id": str(t.assigned_agent_id) if t.assigned_agent_id else None,
        "retry_count": getattr(t, "retry_count", 0) or 0,
        "error_message": t.error_message,
        "created_at": _fmt_dt(t.created_at),
        "updated_at": _fmt_dt(t.updated_at),
    }


def _serialize_run(r: Run, include_log: bool = False) -> dict[str, Any]:
    out = {
        "id": str(r.id),
        "agent_id": str(r.agent_id) if r.agent_id else None,
        "task_id": str(r.task_id) if r.task_id else None,
        "started_at": _fmt_dt(r.started_at),
        "finished_at": _fmt_dt(r.finished_at),
        "status": r.status,
        "tokens_in": r.tokens_in or 0,
        "tokens_out": r.tokens_out or 0,
        "cost_usd": float(r.cost_usd or 0.0),
        "error_message": r.error_message,
    }
    if include_log:
        out["log"] = r.log if isinstance(r.log, dict) else {}
    return out


def _serialize_agent(a: Agent) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "name": a.name,
        "role": a.role,
        "system_prompt": a.system_prompt or "",
        "tools": a.tools if isinstance(a.tools, list) else [],
        "created_at": _fmt_dt(a.created_at),
    }


def _serialize_review(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "task_id": str(item.task_id) if item.task_id else None,
        "action": item.action if isinstance(item.action, dict) else {},
        "reason": item.reason or "",
        "status": item.status,
        "created_at": _fmt_dt(getattr(item, "created_at", None)),
    }


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    data = _run(_dashboard_data())
    return templates.TemplateResponse(request, "dashboard.html", data)


@router.get("/tasks", response_class=HTMLResponse, include_in_schema=False)
async def tasks_page(
    request: Request,
    state: Optional[str] = None,
    page: int = 1,
    per_page: int = 25,
) -> HTMLResponse:
    if per_page not in (10, 25, 50, 100):
        per_page = 25
    page = max(1, page)
    data = _run(_tasks_data(state, page, per_page))
    return templates.TemplateResponse(request, "tasks.html", data)


@router.get("/agents", response_class=HTMLResponse, include_in_schema=False)
async def agents_page(request: Request) -> HTMLResponse:
    agents = _run(_agents_data())
    return templates.TemplateResponse(
        request, "agents.html", {"agents": agents}
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse, include_in_schema=False)
async def run_detail_page(run_id: uuid.UUID, request: Request) -> HTMLResponse:
    detail = _run(_run_detail(run_id))
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )
    return templates.TemplateResponse(request, "runs.html", {"run": detail})


@router.get("/review", response_class=HTMLResponse, include_in_schema=False)
async def review_page(request: Request) -> HTMLResponse:
    items = _run(_review_data())
    return templates.TemplateResponse(
        request, "review.html", {"items": items}
    )


@router.post("/review/{item_id}/resolve", include_in_schema=False)
async def review_resolve(
    item_id: uuid.UUID,
    decision: str = Form(...),
    note: str = Form(""),
    resolved_by: str = Form(...),
) -> RedirectResponse:
    """Form submit handler for the approve/reject buttons."""
    if decision not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision must be approved or rejected",
        )
    queue = get_default_review_queue()
    queue.resolve(
        item_id=item_id,
        decision=decision,
        resolved_by=resolved_by,
        note=note,
    )
    return RedirectResponse(url="/admin/review", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------
# Exposed for tests
# ---------------------------------------------------------------------

__all__ = [
    "ADMIN_TEMPLATE_DIR",
    "STATIC_DIR",
    "mount_admin",
    "router",
    "templates",
]
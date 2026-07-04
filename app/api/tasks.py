"""Task HTTP router — enqueue, claim, complete, fail, list.

Surface:

* ``POST /api/tasks`` — enqueue a new task (delegates to :class:`TaskQueue`).
* ``GET  /api/tasks/{task_id}`` — fetch one task.
* ``GET  /api/tasks`` — list tasks (filter by state).
* ``POST /api/tasks/{task_id}/claim`` — atomically claim a task for an agent.
* ``POST /api/tasks/{task_id}/complete`` — mark a task completed with output.
* ``POST /api/tasks/{task_id}/fail`` — mark a task failed (with optional retry).

All endpoints return either a :class:`TaskResponse` (Pydantic model) or
a small JSON status object. Errors come back as standard FastAPI
``HTTPException`` with sensible status codes.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.db import session_scope
from app.models import Task, TaskState, utc_now
from app.orchestrator.queue import (
    TaskCreate,
    TaskQueue,
    TaskResponse,
    get_default_queue,
)

router = APIRouter()


# ---------------------------------------------------------------------
# Request/response models.
# ---------------------------------------------------------------------


class TaskEnqueueRequest(BaseModel):
    """Body for ``POST /api/tasks``."""

    input_payload: dict[str, Any] = Field(default_factory=dict)
    source_doc_id: Optional[uuid.UUID] = None
    max_retries: int = Field(default=3, ge=0, le=10)


class TaskClaimRequest(BaseModel):
    """Body for ``POST /api/tasks/{id}/claim``."""

    agent_id: uuid.UUID


class TaskCompleteRequest(BaseModel):
    """Body for ``POST /api/tasks/{id}/complete``."""

    output_payload: dict[str, Any] = Field(default_factory=dict)


class TaskFailRequest(BaseModel):
    """Body for ``POST /api/tasks/{id}/fail``."""

    error_message: str = Field(..., min_length=1, max_length=10_000)
    retry: bool = True


class TaskListResponse(BaseModel):
    """Response body for ``GET /api/tasks``."""

    count: int
    tasks: list[TaskResponse]


# ---------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a new task",
)
async def enqueue_task(body: TaskEnqueueRequest) -> TaskResponse:
    """Insert a new pending task into the durable queue."""
    queue = get_default_queue()
    created = await queue.enqueue(
        TaskCreate(
            input_payload=body.input_payload,
            source_doc_id=body.source_doc_id,
            max_retries=body.max_retries,
        )
    )
    return TaskResponse.model_validate(created)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Fetch a single task by id",
)
async def get_task(task_id: uuid.UUID) -> TaskResponse:
    async with session_scope() as session:
        row = await session.get(Task, task_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return TaskResponse.model_validate(row)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks (optional state filter)",
)
async def list_tasks(
    state: Optional[TaskState] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    async with session_scope() as session:
        stmt = select(Task)
        if state is not None:
            stmt = stmt.where(Task.state == state.value)
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
    return TaskListResponse(
        count=len(rows),
        tasks=[TaskResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/{task_id}/claim",
    response_model=TaskResponse,
    summary="Atomically claim a task for an agent",
)
async def claim_task(task_id: uuid.UUID, body: TaskClaimRequest) -> TaskResponse:
    """Mark ``task_id`` as claimed by ``body.agent_id``.

    The task must be in ``PENDING`` state and not have an active lease.
    Uses ``FOR UPDATE SKIP LOCKED`` inside :meth:`TaskQueue.claim`.
    Note: the current :class:`TaskQueue.claim` API pulls the *next*
    available task rather than a specific ``task_id`` — we therefore
    look up the row after the call and verify it matches the
    requested id, raising 409 on a mismatch.
    """
    queue = get_default_queue()
    claimed = await queue.claim(agent_id=body.agent_id)
    if claimed is None or str(claimed.id) != str(task_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task {task_id} is not claimable (wrong state or active lease)",
        )
    return TaskResponse.model_validate(claimed)


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Mark a task completed with output payload",
)
async def complete_task(
    task_id: uuid.UUID, body: TaskCompleteRequest
) -> TaskResponse:
    queue = get_default_queue()
    try:
        completed = await queue.complete(
            task_id=task_id, output_payload=body.output_payload
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return TaskResponse.model_validate(completed)


@router.post(
    "/{task_id}/fail",
    response_model=TaskResponse,
    summary="Mark a task failed (or re-enqueue if retries remain)",
)
async def fail_task(task_id: uuid.UUID, body: TaskFailRequest) -> TaskResponse:
    queue = get_default_queue()
    try:
        failed = await queue.fail(
            task_id=task_id, error_message=body.error_message, retry=body.retry
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return TaskResponse.model_validate(failed)


@router.post(
    "/recover",
    summary="Reclaim stale tasks whose lease has expired",
)
async def recover_stale_tasks() -> dict[str, int]:
    """Sweep task rows whose ``lease_until`` has passed and return them to PENDING."""
    queue = get_default_queue()
    count = await queue.recover_stale_tasks()
    return {"recovered": count}
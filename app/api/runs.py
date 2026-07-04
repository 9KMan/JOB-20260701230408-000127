"""Run HTTP router — read-only audit endpoints for agent runs.

Surface:

* ``GET /api/runs/{run_id}`` — fetch one run row.
* ``GET /api/runs`` — list runs (filter by agent_id, task_id, status).

Runs are append-only audit records: each entry captures a single agent
execution attempt with timing, token usage, cost, and a JSONB log. There
are no write endpoints on this router — runs are created by the
orchestrator during workflow execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.db import session_scope
from app.models import Run, RunStatus

router = APIRouter()


# ---------------------------------------------------------------------
# Response models.
# ---------------------------------------------------------------------


class RunResponse(BaseModel):
    """Wire format for a single run row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error_message: Optional[str] = None
    log: dict[str, Any] = Field(default_factory=dict)


class RunListResponse(BaseModel):
    count: int
    runs: list[RunResponse]


# ---------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Fetch a single run by id",
)
async def get_run(run_id: uuid.UUID) -> RunResponse:
    async with session_scope() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found",
        )
    return RunResponse.model_validate(row)


@router.get(
    "",
    response_model=RunListResponse,
    summary="List runs (filterable by agent / task / status)",
)
async def list_runs(
    agent_id: Optional[uuid.UUID] = Query(default=None),
    task_id: Optional[uuid.UUID] = Query(default=None),
    run_status: Optional[RunStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    async with session_scope() as session:
        stmt = select(Run)
        if agent_id is not None:
            stmt = stmt.where(Run.agent_id == agent_id)
        if task_id is not None:
            stmt = stmt.where(Run.task_id == task_id)
        if run_status is not None:
            stmt = stmt.where(Run.status == run_status.value)
        stmt = stmt.order_by(Run.started_at.desc().nullslast()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
    return RunListResponse(
        count=len(rows),
        runs=[RunResponse.model_validate(r) for r in rows],
    )
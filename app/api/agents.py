"""Agent HTTP router — register, fetch, list, run.

Surface:

* ``POST /api/agents`` — register a new agent definition.
* ``GET  /api/agents/{agent_id}`` — fetch one agent.
* ``GET  /api/agents`` — list agents (filter by role).
* ``POST /api/agents/{agent_id}/run`` — enqueue + run a task with this agent.

The run endpoint creates a fresh :class:`Task` row, then dispatches it
through :func:`app.orchestrator.langgraph_flow.run_workflow` so the
workflow engine can claim it, run it, and either complete or hit the
decision boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.db import session_scope
from app.models import Agent, AgentRole, Task, utc_now
from app.models.task import TaskState
from app.orchestrator.agent import AgentResult, Tool
from app.orchestrator.langgraph_flow import run_workflow
from app.orchestrator.queue import (
    TaskCreate,
    TaskQueue,
    TaskResponse,
    get_default_queue,
)

router = APIRouter()


# ---------------------------------------------------------------------
# Request / response models.
# ---------------------------------------------------------------------


class AgentRegisterRequest(BaseModel):
    """Body for ``POST /api/agents``."""

    name: str = Field(..., min_length=1, max_length=200)
    role: AgentRole = AgentRole.CUSTOM
    config: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str = Field(default="", max_length=20_000)
    tools: list[Tool] = Field(default_factory=list)


class AgentResponse(BaseModel):
    """Wire format for an agent row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str
    config: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str = ""
    tools: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class AgentListResponse(BaseModel):
    count: int
    agents: list[AgentResponse]


class AgentRunRequest(BaseModel):
    """Body for ``POST /api/agents/{agent_id}/run``."""

    input_payload: dict[str, Any] = Field(default_factory=dict)
    source_doc_id: Optional[uuid.UUID] = None
    wait: bool = Field(
        default=False,
        description=(
            "When true, block until the workflow reaches a terminal state "
            "and return the AgentResult inline. When false (default), "
            "return immediately with the enqueued task and let the caller "
            "poll."
        ),
    )


class AgentRunResponse(BaseModel):
    task: TaskResponse
    result: Optional[dict[str, Any]] = None
    status: str


# ---------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent",
)
async def register_agent(body: AgentRegisterRequest) -> AgentResponse:
    async with session_scope() as session:
        agent = Agent(
            name=body.name,
            role=body.role.value,
            config=body.config,
            system_prompt=body.system_prompt,
            tools=[t.model_dump(mode="json") for t in body.tools],
        )
        session.add(agent)
        await session.flush()
        return AgentResponse.model_validate(agent)


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Fetch one agent by id",
)
async def get_agent(agent_id: uuid.UUID) -> AgentResponse:
    async with session_scope() as session:
        row = await session.get(Agent, agent_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )
    return AgentResponse.model_validate(row)


@router.get(
    "",
    response_model=AgentListResponse,
    summary="List agents (optional role filter)",
)
async def list_agents(
    role: Optional[AgentRole] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AgentListResponse:
    async with session_scope() as session:
        stmt = select(Agent)
        if role is not None:
            stmt = stmt.where(Agent.role == role.value)
        stmt = stmt.order_by(Agent.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
    return AgentListResponse(
        count=len(rows),
        agents=[AgentResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/{agent_id}/run",
    response_model=AgentRunResponse,
    summary="Run a task with the given agent",
)
async def run_agent(agent_id: uuid.UUID, body: AgentRunRequest) -> AgentRunResponse:
    """Enqueue a task for ``agent_id`` and optionally run it to completion."""
    # Verify the agent exists; FastAPI-friendly 404 if not.
    async with session_scope() as session:
        agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    queue = get_default_queue()
    task = await queue.enqueue(
        TaskCreate(
            input_payload={
                **body.input_payload,
                "_agent_id": str(agent_id),
            },
            source_doc_id=body.source_doc_id,
        )
    )
    task_resp = TaskResponse.model_validate(task)

    if not body.wait:
        return AgentRunResponse(task=task_resp, status="enqueued")

    # Run synchronously through the LangGraph workflow. The agent id
    # is already embedded in the task's input_payload under ``_agent_id``
    # so the workflow runtime picks the right Agent instance.
    try:
        result: AgentResult = await run_workflow(task_id=task.id)
    except Exception as exc:  # noqa: BLE001 — surface the error in the response
        return AgentRunResponse(
            task=task_resp,
            status="failed",
            result={"error": repr(exc)},
        )

    # Refresh the task row so we see the post-run state.
    async with session_scope() as session:
        row = await session.get(Task, task.id)
    task_resp = TaskResponse.model_validate(row) if row else task_resp

    return AgentRunResponse(
        task=task_resp,
        status=result.status if hasattr(result, "status") else "completed",
        result=(
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else {"output": getattr(result, "final_output", None)}
        ),
    )
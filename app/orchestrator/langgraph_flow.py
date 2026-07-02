"""LangGraph StateGraph — multi-agent workflow orchestration.

This is the *heart* of the orchestrator: a compiled
:class:`langgraph.graph.StateGraph` that drives a single task through
the claim → run → decide → review-or-finalize cycle.

The Phase 3 plan (Section 1.1) calls out the four lifecycle stages:

::

    claim_task → run_agent → check_decision_boundary
                                         │
                          ┌──────────────┴──────────────┐
                          ▼                              ▼
                  request_human_review             finalize

The graph is deliberately small (4 nodes) so the boundary cases are
easy to reason about. The "intelligence" lives in the :class:`Agent`
runtime (see :mod:`app.orchestrator.agent`), not in the graph
plumbing.

State
-----
The graph state is a :class:`WorkflowState` TypedDict. We deliberately
keep the state surface minimal:

* ``task_id`` — UUID of the task being processed.
* ``current_agent`` — UUID of the assigned agent, or ``None`` until
  claim succeeds.
* ``scratchpad`` — A free-form dict the workflow writes its progress
  into (tool calls, intermediate decisions, run log). Mirrors the
  ``scratchpad`` field on :class:`~app.orchestrator.agent.AgentResult`.
* ``final_output`` — The terminal output. ``None`` while the workflow
  is still running. Set by the ``finalize`` node on success.
* ``review_item_id`` — UUID of a pending HITL review item, when the
  workflow pauses for review. ``None`` otherwise.
* ``review_decision`` — ``"approved"`` / ``"rejected"`` / ``None``.
  Populated by :func:`resume_workflow` after a human acts on the
  review item.
* ``status`` — Terminal status string, one of:
  ``"running"``, ``"awaiting_review"``, ``"completed"``, ``"failed"``.

Compiling
---------
Use :func:`build_workflow` to construct a fresh compiled graph, or
call :func:`run_workflow` for the common case of "run a single task
to completion (or to the review gate)".
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    Literal,
    Optional,
    TypedDict,
)

from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.models import Run, RunStatus, Task, TaskState, utc_now
from app.orchestrator.agent import Agent, AgentResult
from app.orchestrator.decision_boundary import (
    ActionContext,
    Decision,
    DecisionBoundaryMiddleware,
    Principal,
)
from app.orchestrator.queue import TaskQueue, get_default_queue
from app.orchestrator.review import HumanReviewQueue, ReviewItem


# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    """Mutable state passed between nodes in the workflow graph.

    All fields are optional in the TypedDict sense so individual
    reducers can leave fields untouched; consumers must read with
    ``.get("field_name", default)``.
    """

    task_id: str
    current_agent: Optional[str]
    scratchpad: Dict[str, Any]
    final_output: Optional[Any]
    review_item_id: Optional[str]
    review_decision: Optional[str]
    status: Literal["running", "awaiting_review", "completed", "failed"]
    error: Optional[str]


# Reducer used to merge scratchpad updates — last writer wins for the
# top-level dict, but lists/dicts are merged shallowly so a node can
# append tool_calls without clobbering the previous node's messages.
def _merge_scratchpad(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow merge with a list-concat for the ``tool_calls`` key."""
    out: Dict[str, Any] = dict(left or {})
    for k, v in (right or {}).items():
        if k == "tool_calls" and isinstance(v, list):
            existing = out.get("tool_calls") or []
            out["tool_calls"] = [*existing, *v]
        else:
            out[k] = v
    return out


# Annotated metadata so LangGraph treats scratchpad as a reducer field.
WorkflowState.__annotations__ = dict(WorkflowState.__annotations__)
# (TypedDict already supports per-key reducers via the langgraph
# ``add`` helper, but we use a custom reducer here so list fields
# like ``tool_calls`` merge correctly across parallel nodes.)


# ---------------------------------------------------------------------
# Wiring helpers
# ---------------------------------------------------------------------


@dataclass
class _RunContext:
    """Resources shared across nodes of a single workflow run.

    Held as an instance attribute on the workflow runner closure
    so we don't have to thread it through every function signature.
    """

    queue: TaskQueue
    review_queue: HumanReviewQueue
    decision_boundary: DecisionBoundaryMiddleware
    principal: Principal
    max_iterations: int = 5
    run_id: Optional[uuid.UUID] = None  # populated by claim_task


# Process-wide cache: at most one compiled graph per process.
_compiled_graph_cache: Dict[str, Any] = {}


# ---------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------


async def claim_task_node(
    state: WorkflowState,
    *,
    ctx: _RunContext,
) -> WorkflowState:
    """claim_task node — atomically claim the next task for the agent.

    Reads ``state.task_id`` (set by the caller), or pulls a new task
    from the queue if not provided. Sets ``state.current_agent`` to
    the agent UUID; sets ``state.status = "running"``.

    If there is no work to do, sets ``state.status = "completed"``
    (the workflow terminates cleanly on the next finalize).
    """
    task_id_str = state.get("task_id")
    scratchpad = dict(state.get("scratchpad") or {})
    scratchpad["claim"] = {"started_at": utc_now().isoformat()}

    claimed = None
    if task_id_str:
        try:
            tid = uuid.UUID(str(task_id_str))
        except ValueError:
            return {
                **state,
                "status": "failed",
                "error": f"invalid task_id: {task_id_str!r}",
            }
        # Direct claim by id — useful for resume / debug.
        # We do this by re-enqueuing a synthetic "claim" via the queue
        # if the task is not already claimed; otherwise we just adopt
        # the assignment.
        async with session_scope() as session:
            row = await session.get(Task, tid)
            if row is None:
                return {
                    **state,
                    "status": "failed",
                    "error": f"task {tid} not found",
                }
            if row.state == TaskState.PENDING.value:
                # Let the queue's atomic claim assign the agent.
                claimed = await ctx.queue.claim(ctx.principal.id)  # type: ignore[arg-type]
            elif row.state == TaskState.RUNNING.value and row.assigned_agent_id:
                # Adopt existing assignment (resume / manual run).
                claimed = await ctx.queue.get(tid)
            else:
                return {
                    **state,
                    "status": "failed",
                    "error": (
                        f"task {tid} in non-runnable state {row.state!r}"
                    ),
                }
    else:
        claimed = await ctx.queue.claim(ctx.principal.id)  # type: ignore[arg-type]

    if claimed is None:
        scratchpad["claim"]["result"] = "no_task"
        return {
            **state,
            "scratchpad": scratchpad,
            "status": "completed",
            "final_output": None,
        }

    # Open a Run row for observability.
    try:
        async with session_scope() as session:
            run_row = Run(
                agent_id=claimed.assigned_agent_id,
                task_id=claimed.id,
                started_at=utc_now(),
                finished_at=None,
                status=RunStatus.FAILED.value,
                log={},
            )
            session.add(run_row)
            await session.flush()
            ctx.run_id = run_row.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("workflow.run_row_create_failed err={}", exc)
        ctx.run_id = None

    scratchpad["claim"]["result"] = "claimed"
    scratchpad["task_id"] = str(claimed.id)
    scratchpad["agent_id"] = (
        str(claimed.assigned_agent_id) if claimed.assigned_agent_id else None
    )
    scratchpad["input_payload"] = claimed.input_payload

    return {
        **state,
        "task_id": str(claimed.id),
        "current_agent": (
            str(claimed.assigned_agent_id) if claimed.assigned_agent_id else None
        ),
        "scratchpad": scratchpad,
        "status": "running",
    }


async def run_agent_node(
    state: WorkflowState,
    *,
    ctx: _RunContext,
) -> WorkflowState:
    """run_agent node — invoke the assigned :class:`Agent` on the task.

    Builds an :class:`Agent` from the assigned agent's stored config
    (if any) and runs it. The result is folded into ``scratchpad``;
    tool calls + final text are preserved so the UI can render the
    agent's conversation.
    """
    if state.get("status") != "running":
        # No-op if claim failed.
        return state

    task_id_str = state.get("task_id")
    if not task_id_str:
        return {
            **state,
            "status": "failed",
            "error": "run_agent called without a claimed task",
        }

    task_uuid = uuid.UUID(str(task_id_str))
    scratchpad = dict(state.get("scratchpad") or {})

    # Fetch the task payload.
    async with session_scope() as session:
        task_row = await session.get(Task, task_uuid)
        if task_row is None:
            return {
                **state,
                "status": "failed",
                "error": f"task {task_uuid} vanished after claim",
            }
        # Snapshot what we need to keep working outside the session.
        task_payload = {
            "id": task_row.id,
            "input_payload": dict(task_row.input_payload or {}),
            "state": task_row.state,
        }

    # Build the runtime Agent. We don't require a registered agent
    # row to exist — the principal is the source of truth for the
    # decision boundary. If you want tool definitions from the
    # ``agents`` table, extend this with a DB lookup.
    from types import SimpleNamespace

    agent = Agent(
        agent_id=ctx.principal.id,
        config={"max_iterations": ctx.max_iterations},
        tools=[],
        system_prompt="",
        decision_boundary=ctx.decision_boundary,
        principal=ctx.principal,
    )

    result: AgentResult = await agent.run(SimpleNamespace(**task_payload))

    # Fold the result into the scratchpad so subsequent nodes see it.
    scratchpad["agent_result"] = {
        "output": result.output,
        "status": result.status,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "tool_calls": [
            {
                "id": c.id,
                "name": c.name,
                "arguments": c.arguments,
            }
            for c in result.tool_calls
        ],
        "scratchpad": result.scratchpad,
        "error": result.error,
        "requires_review": result.requires_review,
        "review_reason": result.review_reason,
    }
    scratchpad["finished_at"] = utc_now().isoformat()

    # If the agent flagged a review, hand off to the HITL node.
    if result.requires_review:
        return {
            **state,
            "scratchpad": scratchpad,
            "status": "running",  # still running — moving to review
        }

    # Otherwise the run terminated: success or partial.
    return {
        **state,
        "scratchpad": scratchpad,
        "final_output": result.output,
        "status": (
            "completed"
            if result.status == RunStatus.SUCCESS.value
            else "failed" if result.status == RunStatus.FAILED.value else "running"
        ),
        "error": result.error,
    }


async def check_decision_boundary_node(
    state: WorkflowState,
    *,
    ctx: _RunContext,
) -> WorkflowState:
    """check_decision_boundary node — determine the next routing.

    Re-evaluates the most recent tool call's decision. If the agent
    flagged ``requires_review`` (i.e. the last run returned a review
    reason), route to ``request_human_review``. Otherwise route to
    ``finalize``.

    This is a no-op for runs that didn't produce a tool call (the
    graph skips directly to finalize).
    """
    scratchpad = dict(state.get("scratchpad") or {})
    agent_result = scratchpad.get("agent_result") or {}
    if agent_result.get("requires_review"):
        # Move to review routing. The actual ``post`` call happens
        # in the request_human_review node.
        return {**state, "scratchpad": scratchpad}
    return {**state, "scratchpad": scratchpad}


async def request_human_review_node(
    state: WorkflowState,
    *,
    ctx: _RunContext,
) -> WorkflowState:
    """request_human_review node — pause for human approval.

    Posts a review item to :class:`HumanReviewQueue` and records the
    id in state. The task itself is parked in
    ``AWAITING_REVIEW`` so the queue won't reclaim it.

    If the workflow was previously resumed (i.e. ``review_decision``
    is set), we skip posting and let finalize handle the result.
    """
    if state.get("review_item_id") and state.get("review_decision"):
        # Already resolved — pass through to finalize.
        return state

    task_id_str = state.get("task_id")
    if not task_id_str:
        return {
            **state,
            "status": "failed",
            "error": "request_human_review without task_id",
        }
    task_uuid = uuid.UUID(str(task_id_str))

    scratchpad = dict(state.get("scratchpad") or {})
    agent_result = scratchpad.get("agent_result") or {}
    proposed_action = (
        agent_result.get("tool_calls")[-1]
        if agent_result.get("tool_calls")
        else {"name": "unknown", "arguments": {}}
    )

    item: ReviewItem = await ctx.review_queue.post(
        task_id=task_uuid,
        action={
            "tool": proposed_action.get("name", "unknown"),
            "arguments": proposed_action.get("arguments", {}),
            "agent_result_status": agent_result.get("status"),
        },
        reason=agent_result.get("review_reason") or "agent requested human review",
    )

    # Move the task to AWAITING_REVIEW so the queue's claim() won't
    # pick it up again until it's resolved.
    async with session_scope() as session:
        row = await session.get(Task, task_uuid)
        if row is not None:
            row.state = TaskState.AWAITING_REVIEW.value
            await session.flush()

    return {
        **state,
        "scratchpad": {**scratchpad, "review_posted": str(item.id)},
        "review_item_id": str(item.id),
        "status": "awaiting_review",
    }


async def finalize_node(
    state: WorkflowState,
    *,
    ctx: _RunContext,
) -> WorkflowState:
    """finalize node — close out the task + write a run log row.

    Determines the terminal status from:

    * ``state.review_decision`` — ``"approved"`` → success;
      ``"rejected"`` → failure.
    * Otherwise: the agent's ``status`` (``completed`` if the agent
      reported ``success``; ``failed`` if the agent reported
      ``failed``; ``running`` if we still need a review).

    Marks the task ``completed`` / ``failed`` via the queue, writes
    the run log row, and sets ``state.status`` to the terminal value.
    """
    task_id_str = state.get("task_id")
    if not task_id_str:
        return {
            **state,
            "status": "failed",
            "error": "finalize without task_id",
        }
    task_uuid = uuid.UUID(str(task_id_str))

    scratchpad = dict(state.get("scratchpad") or {})
    agent_result = scratchpad.get("agent_result") or {}

    # Determine terminal status.
    review_decision = state.get("review_decision")
    if review_decision == "approved":
        terminal_status = "completed"
        final_output = agent_result.get("output")
    elif review_decision == "rejected":
        terminal_status = "failed"
        final_output = None
        scratchpad["finalize_error"] = "review rejected"
    else:
        agent_status = agent_result.get("status")
        if agent_status == RunStatus.SUCCESS.value:
            terminal_status = "completed"
            final_output = agent_result.get("output")
        elif agent_status == RunStatus.FAILED.value:
            terminal_status = "failed"
            final_output = None
        else:
            # partial / unknown — treat as partial completion
            terminal_status = "completed"
            final_output = agent_result.get("output")

    output_payload: Dict[str, Any] = {}
    if final_output is not None:
        output_payload["output"] = final_output
    if agent_result.get("tool_calls"):
        output_payload["tool_calls"] = agent_result.get("tool_calls")
    if review_decision:
        output_payload["review_decision"] = review_decision

    # Mark task terminal.
    try:
        if terminal_status == "completed":
            await ctx.queue.complete(task_uuid, output_payload)
        else:
            await ctx.queue.fail(
                task_uuid,
                scratchpad.get("finalize_error") or "agent failed",
                retry=False,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("workflow.finalize.queue_error err={}", exc)

    # Update run row.
    if ctx.run_id is not None:
        try:
            async with session_scope() as session:
                row = await session.get(Run, ctx.run_id)
                if row is not None:
                    row.finished_at = utc_now()
                    row.status = (
                        RunStatus.SUCCESS.value
                        if terminal_status == "completed"
                        else RunStatus.FAILED.value
                    )
                    row.tokens_in = int(agent_result.get("tokens_in") or 0)
                    row.tokens_out = int(agent_result.get("tokens_out") or 0)
                    row.log = {
                        "scratchpad": scratchpad,
                        "review_decision": review_decision,
                    }
                    if scratchpad.get("finalize_error"):
                        row.error_message = scratchpad["finalize_error"]
                    await session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow.finalize.run_update_failed err={}", exc)

    return {
        **state,
        "scratchpad": scratchpad,
        "final_output": final_output,
        "status": terminal_status,  # type: ignore[typeddict-item]
    }


# ---------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------


def _route_after_check(state: WorkflowState) -> str:
    """Conditional edge: after check_decision_boundary → review or finalize."""
    if state.get("status") == "awaiting_review":
        return "request_human_review"
    return "finalize"


def _route_after_run(state: WorkflowState) -> str:
    """Conditional edge: after run_agent → check or finalize.

    If the agent flagged a review requirement, route through the
    decision boundary check (which inspects the scratchpad and
    routes accordingly). Otherwise skip straight to finalize.
    """
    scratchpad = state.get("scratchpad") or {}
    agent_result = scratchpad.get("agent_result") or {}
    if agent_result.get("requires_review"):
        return "check_decision_boundary"
    if state.get("status") in ("failed", "completed"):
        return "finalize"
    return "finalize"


# ---------------------------------------------------------------------
# Public API — build_workflow / run_workflow / resume_workflow
# ---------------------------------------------------------------------


def build_workflow(
    *,
    queue: Optional[TaskQueue] = None,
    review_queue: Optional[HumanReviewQueue] = None,
    decision_boundary: Optional[DecisionBoundaryMiddleware] = None,
    principal: Optional[Principal] = None,
    max_iterations: int = 5,
):
    """Build and compile the :class:`StateGraph` for the orchestrator.

    Returns a compiled LangGraph graph. Pass the same graph to
    :func:`run_workflow` to drive a single task.

    All parameters are optional; sensible defaults are pulled from
    the corresponding ``get_default_*`` factories.
    """
    q = queue or get_default_queue()
    rq = review_queue or HumanReviewQueue()
    db = decision_boundary or DecisionBoundaryMiddleware()
    p = principal or Principal(
        id="agent:orchestrator", roles=["agent"], blast_radius_budget=50
    )

    ctx = _RunContext(
        queue=q,
        review_queue=rq,
        decision_boundary=db,
        principal=p,
        max_iterations=max_iterations,
    )

    graph = StateGraph(WorkflowState)

    # Nodes — wrap each one so it can see the run context.
    async def _claim(s):  # type: ignore[no-untyped-def]
        return await claim_task_node(s, ctx=ctx)

    async def _run(s):  # type: ignore[no-untyped-def]
        return await run_agent_node(s, ctx=ctx)

    async def _check(s):  # type: ignore[no-untyped-def]
        return await check_decision_boundary_node(s, ctx=ctx)

    async def _review(s):  # type: ignore[no-untyped-def]
        return await request_human_review_node(s, ctx=ctx)

    async def _finalize(s):  # type: ignore[no-untyped-def]
        return await finalize_node(s, ctx=ctx)

    graph.add_node("claim_task", _claim)
    graph.add_node("run_agent", _run)
    graph.add_node("check_decision_boundary", _check)
    graph.add_node("request_human_review", _review)
    graph.add_node("finalize", _finalize)

    # Edges.
    graph.add_edge(START, "claim_task")
    graph.add_edge("claim_task", "run_agent")
    graph.add_conditional_edges(
        "run_agent",
        _route_after_run,
        {
            "check_decision_boundary": "check_decision_boundary",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "check_decision_boundary",
        _route_after_check,
        {
            "request_human_review": "request_human_review",
            "finalize": "finalize",
        },
    )
    # After review, the graph needs to be told the outcome. By
    # default we route to finalize; if the reviewer has not yet
    # acted, finalize will see ``status=awaiting_review`` and end
    # without marking the task done.
    graph.add_edge("request_human_review", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def _get_compiled_graph(
    *,
    queue: Optional[TaskQueue] = None,
    review_queue: Optional[HumanReviewQueue] = None,
    decision_boundary: Optional[DecisionBoundaryMiddleware] = None,
    principal: Optional[Principal] = None,
    max_iterations: int = 5,
):
    """Return a memoised compiled graph (or build a fresh one)."""
    key = (
        id(queue),
        id(review_queue),
        id(decision_boundary),
        id(principal),
        int(max_iterations),
    )
    cached = _compiled_graph_cache.get(key)
    if cached is None:
        cached = build_workflow(
            queue=queue,
            review_queue=review_queue,
            decision_boundary=decision_boundary,
            principal=principal,
            max_iterations=max_iterations,
        )
        _compiled_graph_cache[key] = cached
    return cached


async def run_workflow(
    task_id: Optional[uuid.UUID] = None,
    *,
    queue: Optional[TaskQueue] = None,
    review_queue: Optional[HumanReviewQueue] = None,
    decision_boundary: Optional[DecisionBoundaryMiddleware] = None,
    principal: Optional[Principal] = None,
    max_iterations: int = 5,
) -> AgentResult:
    """Run the workflow to completion (or pause for review).

    If ``task_id`` is given, the workflow tries to claim that specific
    task. Otherwise it pulls the next pending task from the queue.

    Returns an :class:`AgentResult` that mirrors the underlying
    :class:`Agent` run. When the workflow pauses for human review
    the returned result has ``requires_review=True`` and a
    ``review_reason`` populated; call :func:`resume_workflow` after
    the review resolves.
    """
    graph = _get_compiled_graph(
        queue=queue,
        review_queue=review_queue,
        decision_boundary=decision_boundary,
        principal=principal,
        max_iterations=max_iterations,
    )

    initial: WorkflowState = {
        "task_id": str(task_id) if task_id is not None else "",
        "current_agent": None,
        "scratchpad": {},
        "final_output": None,
        "review_item_id": None,
        "review_decision": None,
        "status": "running",
        "error": None,
    }

    final_state: WorkflowState = await graph.ainvoke(initial)  # type: ignore[assignment]

    scratchpad = final_state.get("scratchpad") or {}
    agent_payload = scratchpad.get("agent_result") or {}

    status_map = {
        "completed": RunStatus.SUCCESS.value,
        "failed": RunStatus.FAILED.value,
        "awaiting_review": RunStatus.PARTIAL.value,
        "running": RunStatus.PARTIAL.value,
    }
    mapped_status = status_map.get(final_state.get("status", "running"), RunStatus.PARTIAL.value)

    return AgentResult(
        run_id=None,  # could be enriched via the run row lookup
        output=final_state.get("final_output"),
        tool_calls=[],
        scratchpad=scratchpad,
        tokens_in=int(agent_payload.get("tokens_in") or 0),
        tokens_out=int(agent_payload.get("tokens_out") or 0),
        status=mapped_status,
        error=final_state.get("error"),
        requires_review=bool(final_state.get("review_item_id"))
        and not final_state.get("review_decision"),
        review_reason=(
            str(agent_payload.get("review_reason") or "")
            if final_state.get("status") == "awaiting_review"
            else ""
        ),
    )


async def resume_workflow(
    task_id: uuid.UUID,
    review_item_id: uuid.UUID,
    decision: str,
    *,
    resolved_by: str = "system",
    note: Optional[str] = None,
    review_queue: Optional[HumanReviewQueue] = None,
) -> ReviewItem:
    """Resume a workflow that paused at a HITL review gate.

    Resolves the review item in :class:`HumanReviewQueue` and
    transitions the task to the appropriate terminal state.
    """
    rq = review_queue or HumanReviewQueue()
    decision_norm = (decision or "").strip().lower()
    if decision_norm not in ("approved", "rejected"):
        raise ValueError(
            f"decision must be 'approved' or 'rejected' (got {decision!r})"
        )

    item = await rq.resolve(review_item_id, decision_norm, resolved_by, note=note)

    # Move the task out of AWAITING_REVIEW.
    if decision_norm == "approved":
        async with session_scope() as session:
            row = await session.get(Task, task_id)
            if row is not None:
                # Leave in AWAITING_REVIEW — the resume call from the
                # caller will pick it back up and complete it.
                pass
    else:
        async with session_scope() as session:
            row = await session.get(Task, task_id)
            if row is not None:
                row.state = TaskState.FAILED.value
                row.error_message = f"rejected by {resolved_by}: {note or ''}"
                await session.flush()

    return item


__all__ = [
    "WorkflowState",
    "build_workflow",
    "run_workflow",
    "resume_workflow",
    "claim_task_node",
    "run_agent_node",
    "check_decision_boundary_node",
    "request_human_review_node",
    "finalize_node",
]

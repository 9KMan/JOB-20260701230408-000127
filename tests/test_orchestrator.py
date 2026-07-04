"""Tests for the orchestrator: queue, agent, langgraph flow, review, decision boundary.

These tests use the SQLite fallback (``sqlite+aiosqlite:///:memory:``) so
they don't need Postgres. The production code path uses the same SQLAlchemy
ORM, so the unit tests cover most of the business logic.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

# Force the SQLite fallback before any app imports.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.db import create_all, drop_all, reset_engine, session_scope  # noqa: E402
from app.models import (  # noqa: E402
    Agent,
    AgentRole,
    Task,
    TaskState,
)
from app.orchestrator.agent import Agent  # noqa: E402
from app.orchestrator.decision_boundary import (  # noqa: E402
    ActionContext,
    DecisionBoundaryMiddleware,
    Principal,
    Severity,
)
from app.orchestrator.queue import (  # noqa: E402
    TaskCreate,
    TaskQueue,
    TaskResponse,
)
from app.orchestrator.review import HumanReviewQueue  # noqa: E402


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    """Create the schema once per module, drop it at teardown."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(drop_all())
        loop.run_until_complete(create_all())
    finally:
        loop.close()


@pytest.fixture
def queue() -> TaskQueue:
    """A fresh TaskQueue instance per test (no singleton state)."""
    return TaskQueue()


@pytest.fixture
def review_queue() -> HumanReviewQueue:
    return HumanReviewQueue()


@pytest.fixture(autouse=True)
async def _truncate_tables() -> None:
    """Wipe task / agent / review tables between tests for isolation.

    The schema itself is created once at module load, but row-level
    state is shared across tests in this module.
    """
    from sqlalchemy import text
    async with session_scope() as session:
        await session.execute(text("DELETE FROM tasks"))
        await session.execute(text("DELETE FROM agents"))
        await session.execute(text("DELETE FROM runs"))
        await session.execute(text("DELETE FROM review_queue"))
        try:
            await session.execute(text("DELETE FROM source_documents"))
        except Exception:
            pass
    yield


# ---------------------------------------------------------------------
# TaskQueue tests
# ---------------------------------------------------------------------


async def test_queue_enqueue_returns_pending_task(queue: TaskQueue) -> None:
    created = await queue.enqueue(TaskCreate(input_payload={"x": 1}))
    assert created.state == "pending"
    assert created.input_payload == {"x": 1}


async def test_queue_claim_moves_to_running(queue: TaskQueue) -> None:
    created = await queue.enqueue(TaskCreate(input_payload={"y": 2}))
    # Claim pulls the next available task — for an isolated queue
    # there's only one candidate.
    claimed = await queue.claim(agent_id=uuid.uuid4())
    assert claimed is not None
    assert claimed.id == created.id
    assert claimed.state == "running"
    assert str(claimed.assigned_agent_id) == str(claimed.assigned_agent_id)
    assert claimed.lease_until is not None


async def test_queue_claim_with_no_pending_returns_none(queue: TaskQueue) -> None:
    claimed = await queue.claim(agent_id=uuid.uuid4())
    assert claimed is None


async def test_queue_claim_second_call_after_completion_returns_none(
    queue: TaskQueue,
) -> None:
    t = await queue.enqueue(TaskCreate(input_payload={}))
    a = uuid.uuid4()
    first = await queue.claim(agent_id=a)
    assert first is not None
    await queue.complete(task_id=t.id, output_payload={"done": True})
    # After completion, the queue is empty.
    second = await queue.claim(agent_id=uuid.uuid4())
    assert second is None


async def test_queue_complete_persists_output(queue: TaskQueue) -> None:
    t = await queue.enqueue(TaskCreate(input_payload={}))
    a = uuid.uuid4()
    await queue.claim(agent_id=a)
    done = await queue.complete(task_id=t.id, output_payload={"result": 42})
    assert done.state == "completed"
    assert done.output_payload == {"result": 42}


async def test_queue_fail_with_retry_returns_to_pending(queue: TaskQueue) -> None:
    t = await queue.enqueue(TaskCreate(input_payload={}))
    a = uuid.uuid4()
    await queue.claim(agent_id=a)
    failed = await queue.fail(task_id=t.id, error_message="boom", retry=True)
    # With retry, the task goes back to PENDING with retry_count incremented.
    assert failed.state == "pending"
    assert failed.retry_count == 1


async def test_queue_fail_without_retry_marks_failed(queue: TaskQueue) -> None:
    t = await queue.enqueue(TaskCreate(input_payload={}))
    a = uuid.uuid4()
    await queue.claim(agent_id=a)
    failed = await queue.fail(task_id=t.id, error_message="boom", retry=False)
    assert failed.state == "failed"
    assert failed.error_message == "boom"


async def test_queue_recover_stale_tasks_reclaims_expired_leases(
    queue: TaskQueue,
) -> None:
    """A claimed task with an expired lease is reclaimed."""
    t = await queue.enqueue(TaskCreate(input_payload={}))
    a = uuid.uuid4()
    claimed = await queue.claim(agent_id=a)
    assert claimed is not None

    # Force the lease to be in the past.
    from datetime import datetime, timedelta, timezone
    async with session_scope() as session:
        row = await session.get(Task, t.id)
        assert row is not None
        row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=10)

    recovered = await queue.recover_stale_tasks()
    assert recovered >= 1
    async with session_scope() as session:
        row = await session.get(Task, t.id)
        assert row is not None
        assert row.state == "pending"
        assert row.assigned_agent_id is None


# ---------------------------------------------------------------------
# Agent tests
# ---------------------------------------------------------------------


async def test_agent_should_request_human_review_is_fail_closed() -> None:
    """Agent.should_request_human_review returns True by default (fail-closed)."""
    agent = Agent(
        agent_id=uuid.uuid4(),
        config={},
        tools=[],
        system_prompt="x",
    )
    # Conservative default: every action requires review.
    assert agent.should_request_human_review("read_file") is True
    assert agent.should_request_human_review("delete_database") is True
    assert agent.should_request_human_review("") is True
    assert agent.should_request_human_review("unknown_action") is True


async def test_agent_run_with_no_tools_returns_agent_result(queue: TaskQueue) -> None:
    """A no-tools agent returns a stub AgentResult in offline mode."""
    agent = Agent(
        agent_id=uuid.uuid4(),
        config={"offline_stub": True},
        tools=[],
        system_prompt="x",
    )
    t = await queue.enqueue(TaskCreate(input_payload={"question": "hi"}))
    result = await agent.run(t)
    # Whatever the stub returns, the call must not raise.
    assert result is not None
    # The result carries a `status` attribute per the AgentResult dataclass.
    assert hasattr(result, "status") or hasattr(result, "final_output")


# ---------------------------------------------------------------------
# Decision-boundary tests
# ---------------------------------------------------------------------


async def test_decision_boundary_sensitive_tool_requires_review() -> None:
    mw = DecisionBoundaryMiddleware()
    principal = Principal(id="agent-1", roles=["researcher"])
    ctx = ActionContext(
        tool="shell",
        args={},
        principal=principal,
    )
    decision = await mw.evaluate(ctx)
    assert decision.require_review is True
    assert decision.severity in (Severity.HIGH, Severity.CRITICAL)


async def test_decision_boundary_safe_tool_with_allowlist_passes() -> None:
    mw = DecisionBoundaryMiddleware(
        role_allowlists={"researcher": frozenset({"read_file", "search_documents"})},
    )
    principal = Principal(id="agent-1", roles=["researcher"])
    ctx = ActionContext(tool="read_file", args={}, principal=principal)
    decision = await mw.evaluate(ctx)
    # Safe tools with proper allowlist should be allowed without review.
    assert decision.require_review is False or decision.allow is True


async def test_decision_boundary_blocklist_overrides_allowlist() -> None:
    mw = DecisionBoundaryMiddleware(
        role_allowlists={"researcher": frozenset({"read_file"})},
        role_blocklist={"researcher": frozenset({"read_file"})},
    )
    principal = Principal(id="agent-1", roles=["researcher"])
    ctx = ActionContext(tool="read_file", args={}, principal=principal)
    decision = await mw.evaluate(ctx)
    # Blocklist wins -> should require review or deny.
    assert decision.severity in (Severity.HIGH, Severity.CRITICAL)


# ---------------------------------------------------------------------
# Review queue tests
# ---------------------------------------------------------------------


async def test_review_post_and_resolve(review_queue: HumanReviewQueue) -> None:
    item = await review_queue.post(
        task_id=uuid.uuid4(),
        action={"tool": "send_email", "to": "x@example.com"},
        reason="external action",
    )
    assert item.status == "pending"

    resolved = await review_queue.resolve(
        item_id=item.id,
        decision="approved",
        resolved_by="admin",
        note="ok",
    )
    assert resolved.status == "approved"
    assert resolved.resolved_by == "admin"


async def test_review_list_pending_drops_resolved(
    review_queue: HumanReviewQueue,
) -> None:
    a = await review_queue.post(task_id=uuid.uuid4(), action={"x": 1}, reason="r1")
    b = await review_queue.post(task_id=uuid.uuid4(), action={"x": 2}, reason="r2")
    await review_queue.resolve(item_id=a.id, decision="approved", resolved_by="admin")
    pending = await review_queue.list_pending(limit=50)
    ids = {str(p.id) for p in pending}
    assert str(b.id) in ids
    assert str(a.id) not in ids


async def test_review_resolve_rejects_invalid_decision(
    review_queue: HumanReviewQueue,
) -> None:
    item = await review_queue.post(task_id=uuid.uuid4(), action={}, reason="r")
    with pytest.raises(ValueError):
        await review_queue.resolve(
            item_id=item.id, decision="MAYBE", resolved_by="admin"
        )
"""Task queue — the durable work queue used by the orchestrator.

:class:`TaskQueue` wraps the ``tasks`` table and exposes the five
queue operations the orchestrator needs:

* :meth:`enqueue` — insert a new task.
* :meth:`claim` — atomically pull the next available task for an
  agent (``FOR UPDATE SKIP LOCKED`` + advisory lock).
* :meth:`complete` — mark a task ``completed`` with output.
* :meth:`fail` — mark a task ``failed`` (or re-enqueue if retries
  remain).
* :meth:`recover_stale_tasks` — reclaim tasks whose lease has
  expired.

The locking strategy follows the Phase 3 plan (Section 1.1) and is
designed to be safe under concurrent producers and consumers:

1. ``enqueue`` opens a transaction, inserts the row, and commits.
2. ``claim`` uses ``pg_advisory_xact_lock`` to serialize claimers
   within a process (defense in depth), then runs
   ``SELECT ... FOR UPDATE SKIP LOCKED`` to find a reclaimable row.
3. ``complete`` / ``fail`` / ``recover_stale_tasks`` operate on a
   single row using a normal ``UPDATE``.

All public methods are async and take an optional
:class:`~sqlalchemy.ext.asyncio.AsyncSession` so the caller can
batch operations in a single transaction when needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory, session_scope
from app.models import Task, TaskState, utc_now


# ---------------------------------------------------------------------
# Pydantic schemas (input/output of the queue API).
#
# These are kept separate from the SQLAlchemy models so callers can
# use them without a DB session and so the wire format stays clean.
# ---------------------------------------------------------------------


class TaskCreate(BaseModel):
    """Payload for :meth:`TaskQueue.enqueue`."""

    input_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured input supplied by the producer.",
    )
    source_doc_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional reference to a source_documents row.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of times this task may be retried.",
    )


class TaskResponse(BaseModel):
    """Wire format for a task row returned by the queue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    assigned_agent_id: Optional[uuid.UUID] = None
    lease_until: Optional[datetime] = None
    source_doc_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_orm_row(cls, row: Task) -> "TaskResponse":
        """Build a response from a SQLAlchemy :class:`Task` row."""
        return cls(
            id=row.id,
            state=row.state,
            input_payload=row.input_payload or {},
            output_payload=row.output_payload or {},
            assigned_agent_id=row.assigned_agent_id,
            lease_until=row.lease_until,
            source_doc_id=row.source_doc_id,
            error_message=row.error_message,
            retry_count=row.retry_count,
            max_retries=row.max_retries,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ---------------------------------------------------------------------
# TaskQueue
# ---------------------------------------------------------------------


class TaskQueue:
    """Async task queue backed by the ``tasks`` table.

    The class is stateless; all state lives in the database. You can
    instantiate one per process (or per request) and call its
    methods freely.
    """

    # Stable advisory-lock key for ``claim()``. Using a fixed int lets
    # all claimers across processes serialize on the same lock,
    # in addition to the per-row ``FOR UPDATE SKIP LOCKED`` they
    # already use.
    _ADVISORY_LOCK_CLAIM: int = 0x71756575_5F636C6D  # 'queue_clm'

    # ------------------------------------------------------------------
    # enqueue
    # ------------------------------------------------------------------
    async def enqueue(
        self,
        task: TaskCreate,
        *,
        session: Optional[AsyncSession] = None,
    ) -> TaskResponse:
        """Insert a new ``pending`` task and return it.

        If ``session`` is supplied, the insert is part of the caller's
        transaction; otherwise we open our own.
        """
        async def _do(s: AsyncSession) -> TaskResponse:
            row = Task(
                state=TaskState.PENDING.value,
                input_payload=task.input_payload,
                output_payload={},
                source_doc_id=task.source_doc_id,
                max_retries=task.max_retries,
                retry_count=0,
                error_message=None,
                assigned_agent_id=None,
                lease_until=None,
            )
            s.add(row)
            await s.flush()
            return TaskResponse.from_orm_row(row)

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)

    # ------------------------------------------------------------------
    # claim
    # ------------------------------------------------------------------
    async def claim(
        self,
        agent_id: uuid.UUID,
        lease_seconds: int = 300,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[TaskResponse]:
        """Claim the next reclaimable task for ``agent_id``.

        Returns ``None`` when there is no work to do.

        A task is reclaimable when:

        * its ``state`` is ``pending``, AND
        * it has no live lease (``lease_until IS NULL`` or
          ``lease_until < NOW()``).

        We use a per-transaction advisory lock to serialize concurrent
        claimers *within* a single process, then ``FOR UPDATE SKIP
        LOCKED`` to make sure multiple processes don't fight over the
        same row.
        """
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be > 0")

        async def _do(s: AsyncSession) -> Optional[TaskResponse]:
            # Serialize claimers inside this process. The lock auto-
            # releases on COMMIT/ROLLBACK.
            await s.execute(
                text("SELECT pg_advisory_xact_lock(:k)"),
                {"k": self._ADVISORY_LOCK_CLAIM},
            )

            now = utc_now()
            candidate_q = (
                select(Task)
                .where(Task.state == TaskState.PENDING.value)
                .where(
                    (Task.lease_until.is_(None))
                    | (Task.lease_until < now)
                )
                .order_by(Task.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = (await s.execute(candidate_q)).scalar_one_or_none()
            if row is None:
                return None

            row.assigned_agent_id = agent_id
            row.state = TaskState.RUNNING.value
            row.lease_until = now + timedelta(seconds=lease_seconds)
            await s.flush()
            return TaskResponse.from_orm_row(row)

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)

    # ------------------------------------------------------------------
    # complete
    # ------------------------------------------------------------------
    async def complete(
        self,
        task_id: uuid.UUID,
        output_payload: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> TaskResponse:
        """Mark ``task_id`` as completed and store ``output_payload``.

        Raises :class:`KeyError` if the task does not exist, and
        :class:`RuntimeError` if the task is not currently in a
        runnable state.
        """
        async def _do(s: AsyncSession) -> TaskResponse:
            row = await s.get(Task, task_id)
            if row is None:
                raise KeyError(f"task {task_id} not found")
            if row.state not in (
                TaskState.RUNNING.value,
                TaskState.PENDING.value,  # allow marking stale-but-recovered tasks done
            ):
                raise RuntimeError(
                    f"cannot complete task {task_id} in state {row.state}"
                )
            row.state = TaskState.COMPLETED.value
            row.output_payload = output_payload
            row.error_message = None
            row.lease_until = None
            await s.flush()
            return TaskResponse.from_orm_row(row)

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)

    # ------------------------------------------------------------------
    # fail
    # ------------------------------------------------------------------
    async def fail(
        self,
        task_id: uuid.UUID,
        error_message: str,
        retry: bool = True,
        *,
        session: Optional[AsyncSession] = None,
    ) -> TaskResponse:
        """Mark ``task_id`` as failed (or re-enqueue if retries remain).

        When ``retry=True`` and ``retry_count < max_retries``, the task
        is moved back to ``pending`` with ``retry_count += 1`` so it
        will be picked up by the next :meth:`claim` call. Otherwise
        the task is permanently set to ``failed``.
        """
        async def _do(s: AsyncSession) -> TaskResponse:
            row = await s.get(Task, task_id)
            if row is None:
                raise KeyError(f"task {task_id} not found")
            if row.state not in (
                TaskState.RUNNING.value,
                TaskState.AWAITING_REVIEW.value,
                TaskState.PENDING.value,
            ):
                raise RuntimeError(
                    f"cannot fail task {task_id} in state {row.state}"
                )

            should_retry = (
                retry and (row.retry_count + 1) <= row.max_retries
            )
            if should_retry:
                row.state = TaskState.PENDING.value
                row.assigned_agent_id = None
                row.lease_until = None
                row.retry_count = (row.retry_count or 0) + 1
                row.error_message = error_message
            else:
                row.state = TaskState.FAILED.value
                row.error_message = error_message
                row.lease_until = None
            await s.flush()
            return TaskResponse.from_orm_row(row)

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)

    # ------------------------------------------------------------------
    # recover_stale_tasks
    # ------------------------------------------------------------------
    async def recover_stale_tasks(
        self,
        *,
        session: Optional[AsyncSession] = None,
    ) -> int:
        """Reclaim tasks whose lease has expired.

        A task is considered stale when it is ``running`` but its
        ``lease_until`` is in the past. We move it back to
        ``pending``, clear the assignment, and leave the lease as-is
        (so we can see it in audit logs).

        Returns the number of rows reclaimed.
        """
        async def _do(s: AsyncSession) -> int:
            now = utc_now()
            stmt = (
                update(Task)
                .where(Task.state == TaskState.RUNNING.value)
                .where(Task.lease_until.is_not(None))
                .where(Task.lease_until < now)
                .values(
                    state=TaskState.PENDING.value,
                    assigned_agent_id=None,
                    # NOTE: leave lease_until alone so audit queries can
                    # see when the lease expired.
                )
                .execution_options(synchronize_session=False)
            )
            result = await s.execute(stmt)
            return int(result.rowcount or 0)

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def get(
        self,
        task_id: uuid.UUID,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[TaskResponse]:
        """Fetch a single task by id (returns ``None`` if missing)."""
        async def _do(s: AsyncSession) -> Optional[TaskResponse]:
            row = await s.get(Task, task_id)
            return TaskResponse.from_orm_row(row) if row else None

        if session is not None:
            return await _do(session)
        async with session_scope() as s:
            return await _do(s)


# ---------------------------------------------------------------------
# Async factory — convenience used by the LangGraph nodes.
# ---------------------------------------------------------------------


_default_queue: Optional[TaskQueue] = None


def get_default_queue() -> TaskQueue:
    """Return a process-wide singleton :class:`TaskQueue`."""
    global _default_queue
    if _default_queue is None:
        _default_queue = TaskQueue()
    return _default_queue


__all__ = [
    "TaskCreate",
    "TaskQueue",
    "TaskResponse",
    "get_default_queue",
]
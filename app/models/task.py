"""Task ORM model.

A ``Task`` is the unit of work flowing through the orchestrator. It
is enqueued by callers (API, CLI, agent), claimed by an agent, and
either completed or failed.

Key design points:

* ``state`` is a string column storing the ``TaskState`` enum value.
  This keeps the on-disk representation human-readable and queryable
  via raw SQL.
* ``input_payload`` / ``output_payload`` are JSONB so they can hold
  arbitrary structured data without schema migrations.
* ``lease_until`` + ``state`` form the (state, lease_until) composite
  index used by ``TaskQueue.claim`` to find reclaimable work with
  ``FOR UPDATE SKIP LOCKED``.
* ``retry_count`` + ``max_retries`` + ``error_message`` power the
  automatic retry path in ``TaskQueue.fail``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import JSONBDictType as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskState


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A unit of orchestrated work.

    Attributes:
        id: UUID PK.
        state: Current lifecycle state (``TaskState``).
        input_payload: Arbitrary structured input supplied by the
            producer. Always a JSON object on the wire; defaults to
            ``{}``.
        output_payload: Result produced by the assigned agent.
        assigned_agent_id: UUID of the agent that has claimed this
            task, or ``NULL`` when unclaimed.
        lease_until: When the current lease expires. After this time
            (and while still in ``RUNNING``) the task is considered
            stale and may be recovered.
        source_doc_id: Optional foreign-key reference to a
            ``Document`` row in the RAG store (the doc that triggered
            the task).
        error_message: Failure detail, populated by ``TaskQueue.fail``.
        retry_count: Number of times this task has been re-enqueued
            after failure.
        created_at / updated_at: From ``TimestampMixin``.
    """

    __tablename__ = "tasks"

    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskState.PENDING.value,
        server_default=text(f"'{TaskState.PENDING.value}'"),
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    output_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    assigned_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    lease_until: Mapped[Optional[datetime]] = mapped_column(
        # Stored as a timestamptz so server-side NOW() comparisons work.
        # The TIMESTAMPTZ type is exposed via the generic DateTime
        # with timezone=True (Postgres sees it as ``timestamp with
        # time zone``).
        nullable=True,
    )
    source_doc_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )

    # Composite indexes — see TaskQueue.claim() and recover_stale_tasks().
    # Note: ``created_at`` is already indexed by TimestampMixin (with
    # ``index=True``), so we don't redeclare it here.
    __table_args__ = (
        Index(
            "ix_tasks_state_lease_until",
            "state",
            "lease_until",
        ),
        Index("ix_tasks_assigned_agent_id", "assigned_agent_id"),
        Index("ix_tasks_source_doc_id", "source_doc_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Task id={self.id} state={self.state} "
            f"agent={self.assigned_agent_id} retries={self.retry_count}>"
        )


__all__ = ["Task"]
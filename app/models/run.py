"""Run ORM model — per-attempt execution log for an agent.

A ``Run`` records one execution attempt of an agent on a task. It's
the audit row used by the observability stack (Section 4 of the
Phase 3 plan). Token + cost columns let us budget per-agent and
per-run; ``log`` is a JSONB blob with the structured run log
(events, tool calls, intermediate states).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import JSONBDictType as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RunStatus


class Run(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single agent run.

    Attributes:
        id: UUID PK.
        agent_id: FK to ``agents.id``.
        task_id: FK to ``tasks.id`` (the task this run is working on).
        started_at: When the run was launched.
        finished_at: When the run terminated (success or failure).
        status: ``success`` / ``partial`` / ``failed``.
        tokens_in / tokens_out: Total token counters for this run.
        cost_usd: Estimated USD cost of the run.
        error_message: Free-form failure detail.
        log: Structured JSONB log — tool calls, intermediate agent
            messages, retry decisions, etc.
    """

    __tablename__ = "runs"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RunStatus.FAILED.value,
        server_default=text(f"'{RunStatus.FAILED.value}'"),
    )
    tokens_in: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    __table_args__ = (
        Index("ix_runs_status_started_at", "status", "started_at"),
        Index("ix_runs_agent_started_at", "agent_id", "started_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Run id={self.id} agent={self.agent_id} task={self.task_id} "
            f"status={self.status}>"
        )


__all__ = ["Run"]
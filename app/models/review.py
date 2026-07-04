"""ReviewQueueItem ORM model — human-in-the-loop approval queue.

When the decision-boundary middleware decides an action is
high-consequence (Section 1.3 of the Phase 3 plan), the orchestrator
posts an item to ``review_queue`` and pauses the workflow until a
human approves or rejects it.

Items are immutable once resolved (``resolved_at`` + ``resolved_by``
+ ``note`` form the audit record). See ``orchestrator.review`` for
the queue API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import JSONBDictType as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ReviewStatus


class ReviewQueueItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single queued human-review request.

    Attributes:
        id: UUID PK.
        task_id: FK to the task that produced the gated action.
        action: JSONB blob describing the proposed action (tool name,
            arguments, expected effect, blast radius, etc.).
        reason: Human-readable reason the action was gated (e.g.
            ``"blast_radius: 12 records affected"``).
        status: ``pending`` / ``approved`` / ``rejected``.
        resolved_at: When the item was resolved (NULL while pending).
        resolved_by: Identifier of the human who resolved it.
        note: Optional note from the resolver explaining the decision.
    """

    __tablename__ = "review_queue"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    reason: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        server_default=text("''"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewStatus.PENDING.value,
        server_default=text(f"'{ReviewStatus.PENDING.value}'"),
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Common query: list pending items assigned to a principal.
        Index(
            "ix_review_queue_status_created_at",
            "status",
            "created_at",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReviewQueueItem id={self.id} task={self.task_id} "
            f"status={self.status}>"
        )


__all__ = ["ReviewQueueItem"]
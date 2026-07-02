"""Human review queue — durable HITL approval queue.

:class:`HumanReviewQueue` writes to the ``review_queue`` table and
provides:

* :meth:`post` — enqueue a review item and (optionally) return a
  ``Future`` that will be resolved when a human acts on it.
* :meth:`resolve` — mark a queued item approved/rejected and resume
  the waiting workflow.
* :meth:`wait` — block until a review item is resolved (async).
* :meth:`list_pending` — query the pending items.

The in-memory ``Future`` map is for unit-testing and for single-
process deployments. For multi-worker production deployments you
would back this with Postgres ``LISTEN/NOTIFY`` or a Redis pub/sub;
the interface is identical so the swap is local.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import select

from app.db import session_scope
from app.models import ReviewQueueItem, ReviewStatus, utc_now
from app.models.enums import Severity


class ReviewItem(BaseModel):
    """Wire-format view of a queued review item."""

    id: uuid.UUID
    task_id: uuid.UUID
    action: Dict[str, Any]
    reason: str
    status: str
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    note: Optional[str]
    severity: Optional[str] = None

    @classmethod
    def from_row(cls, row: ReviewQueueItem) -> "ReviewItem":
        action = dict(row.action or {})
        severity = action.pop("__severity__", None)
        return cls(
            id=row.id,
            task_id=row.task_id,
            action=action,
            reason=row.reason,
            status=row.status,
            resolved_at=row.resolved_at,
            resolved_by=row.resolved_by,
            note=row.note,
            severity=severity,
        )


class HumanReviewQueue:
    """Async queue for human-in-the-loop approvals.

    The queue keeps an in-memory ``Future`` per pending item so
    callers awaiting :meth:`wait` are notified when :meth:`resolve`
    is invoked for the same item id. Use a single
    :class:`HumanReviewQueue` instance per process.
    """

    def __init__(self) -> None:
        self._futures: Dict[uuid.UUID, asyncio.Future[ReviewItem]] = {}

    # ------------------------------------------------------------------
    # post
    # ------------------------------------------------------------------
    async def post(
        self,
        task_id: uuid.UUID,
        action: Dict[str, Any],
        reason: str,
        severity: Optional[Severity] = None,
        *,
        await_resolution: bool = False,
    ) -> ReviewItem:
        """Enqueue a review item.

        When ``await_resolution=True``, returns the resolved item
        (after a human calls :meth:`resolve`). When ``False`` (the
        default), returns the pending item immediately.

        The returned item is also a handle: callers can pass its
        ``id`` to :meth:`wait` to block.
        """
        # Stash severity inside the action JSON so it survives the
        # round-trip; pop it back out in ReviewItem.from_row.
        action_with_sev: Dict[str, Any] = dict(action)
        if severity is not None:
            action_with_sev["__severity__"] = severity.value

        async with session_scope() as session:
            row = ReviewQueueItem(
                task_id=task_id,
                action=action_with_sev,
                reason=reason,
                status=ReviewStatus.PENDING.value,
                resolved_at=None,
                resolved_by=None,
                note=None,
            )
            session.add(row)
            await session.flush()
            item_id = row.id
            item = ReviewItem.from_row(row)

        # Optionally block until resolved.
        if not await_resolution:
            return item

        return await self.wait(item_id)

    # ------------------------------------------------------------------
    # wait
    # ------------------------------------------------------------------
    async def wait(self, item_id: uuid.UUID) -> ReviewItem:
        """Block until ``item_id`` is resolved.

        Raises :class:`asyncio.TimeoutError` if the queue's internal
        wait is interrupted, or :class:`KeyError` if the item does
        not exist (it was already resolved and forgotten).
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ReviewItem] = loop.create_future()
        self._futures[item_id] = future
        try:
            return await future
        finally:
            self._futures.pop(item_id, None)

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------
    async def resolve(
        self,
        item_id: uuid.UUID,
        decision: str,
        resolved_by: str,
        note: Optional[str] = None,
    ) -> ReviewItem:
        """Mark ``item_id`` approved/rejected and resume waiters.

        ``decision`` must be ``"approved"`` or ``"rejected"``.
        """
        decision_norm = (decision or "").strip().lower()
        if decision_norm not in (
            ReviewStatus.APPROVED.value,
            ReviewStatus.REJECTED.value,
        ):
            raise ValueError(
                f"decision must be 'approved' or 'rejected', got {decision!r}"
            )

        async with session_scope() as session:
            row = await session.get(ReviewQueueItem, item_id)
            if row is None:
                raise KeyError(f"review item {item_id} not found")
            if row.status != ReviewStatus.PENDING.value:
                raise RuntimeError(
                    f"review item {item_id} already resolved (status={row.status})"
                )
            row.status = decision_norm
            row.resolved_at = utc_now()
            row.resolved_by = resolved_by
            row.note = note
            await session.flush()
            item = ReviewItem.from_row(row)

        # Wake up any waiter.
        future = self._futures.pop(item_id, None)
        if future is not None and not future.done():
            future.set_result(item)
        return item

    # ------------------------------------------------------------------
    # list_pending
    # ------------------------------------------------------------------
    async def list_pending(
        self,
        limit: int = 100,
    ) -> List[ReviewItem]:
        """Return up to ``limit`` pending review items."""
        async with session_scope() as session:
            stmt = (
                select(ReviewQueueItem)
                .where(ReviewQueueItem.status == ReviewStatus.PENDING.value)
                .order_by(ReviewQueueItem.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [ReviewItem.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------
    async def get(self, item_id: uuid.UUID) -> Optional[ReviewItem]:
        """Fetch a single review item (or ``None``)."""
        async with session_scope() as session:
            row = await session.get(ReviewQueueItem, item_id)
            return ReviewItem.from_row(row) if row else None


# pydantic BaseModel is imported above for the ReviewItem class.

__all__ = ["HumanReviewQueue", "ReviewItem"]
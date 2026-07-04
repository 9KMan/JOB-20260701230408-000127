"""Review HTTP router — human-in-the-loop approval endpoints.

Surface:

* ``GET  /api/review/pending`` — list items still awaiting a human decision.
* ``POST /api/review/{item_id}/resolve`` — approve or reject a queued item.

The :class:`HumanReviewQueue` owns the in-process Future-based gating
machinery; this router just translates HTTP into queue method calls.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.orchestrator.review import (
    HumanReviewQueue,
    ReviewItem,
    get_default_review_queue,
)

router = APIRouter()


# ---------------------------------------------------------------------
# Request/response models.
# ---------------------------------------------------------------------


class ReviewResolveRequest(BaseModel):
    """Body for ``POST /api/review/{id}/resolve``."""

    decision: str = Field(..., description="Either 'approved' or 'rejected'")
    note: str = Field(default="", max_length=10_000)
    resolved_by: str = Field(..., min_length=1, max_length=200)

    @field_validator("decision")
    @classmethod
    def _validate_decision(cls, v: str) -> str:
        if v not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return v


class ReviewItemResponse(BaseModel):
    """Wire format for a queued review item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    action: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    status: str
    resolved_by: Optional[str] = None
    note: Optional[str] = None


class ReviewResolveResponse(BaseModel):
    id: uuid.UUID
    status: str
    resolved_by: str
    note: str


# ---------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------


@router.get(
    "/pending",
    response_model=list[ReviewItemResponse],
    summary="List review items awaiting a human decision",
)
async def list_pending() -> list[ReviewItemResponse]:
    queue = get_default_review_queue()
    pending = await queue.list_pending(limit=200)
    return [ReviewItemResponse.model_validate(item) for item in pending]


@router.post(
    "/{item_id}/resolve",
    response_model=ReviewResolveResponse,
    summary="Approve or reject a queued review item",
)
async def resolve_review(item_id: uuid.UUID, body: ReviewResolveRequest) -> ReviewResolveResponse:
    queue = get_default_review_queue()
    item = queue.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review item {item_id} not found",
        )
    if item.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review item {item_id} is already {item.status}",
        )

    queue.resolve(
        item_id=item_id,
        decision=body.decision,  # type: ignore[arg-type]
        resolved_by=body.resolved_by,
        note=body.note,
    )

    return ReviewResolveResponse(
        id=item_id,
        status=body.decision,
        resolved_by=body.resolved_by,
        note=body.note,
    )


def _coerce_to_wire(item: ReviewItem) -> ReviewItemResponse:
    """Helper for tests/UI that build a wire-format response from a queue item."""
    return ReviewItemResponse.model_validate(item)
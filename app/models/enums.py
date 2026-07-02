"""Enumerations used across the orchestration data model.

These enums back the PostgreSQL task / agent / run / review tables and are
exposed to LangGraph / Agent code as plain Python enums.

The enums inherit from ``str`` so they can be serialized as strings
directly by Pydantic, JSON encoders, and SQLAlchemy.
"""

from __future__ import annotations

import enum


class TaskState(str, enum.Enum):
    """Lifecycle states of an orchestrated Task.

    Transitions::

        PENDING ──claim()──► RUNNING ──complete()──► COMPLETED
                              │
                              ├──fail()──► FAILED ──retry()──► PENDING
                              │
                              └──lease expiry──► PENDING (recovered)

    ``AWAITING_REVIEW`` is used when a high-consequence action is gated
    behind a human review (see ``orchestrator.decision_boundary``).
    """

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRole(str, enum.Enum):
    """Role classification for an agent in the multi-agent topology.

    Matches the role taxonomy described in the Phase 3 plan (Section 1).
    ORCHESTRATOR agents own the graph; the others are leaf specialists
    that the orchestrator delegates to.
    """

    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"
    CUSTOM = "custom"


class Severity(str, enum.Enum):
    """Severity classification used by the decision-boundary middleware
    and review queue.

    Severity increases monotonically. ``CRITICAL`` actions are always
    blocked without human review.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RunStatus(str, enum.Enum):
    """Status of an individual agent Run (one execution attempt)."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    """Status of a queued human-review item."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


__all__ = [
    "TaskState",
    "AgentRole",
    "Severity",
    "RunStatus",
    "ReviewStatus",
]
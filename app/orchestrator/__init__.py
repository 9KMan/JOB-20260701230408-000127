"""Orchestrator package — the heart of the multi-agent system.

Modules:

* :mod:`app.orchestrator.queue` — :class:`TaskQueue` (enqueue / claim
  / complete / fail / recover_stale_tasks).
* :mod:`app.orchestrator.agent` — :class:`Agent` (runs an LLM tool
  loop, owns the decision-boundary hook).
* :mod:`app.orchestrator.langgraph_flow` — compiled LangGraph
  :class:`StateGraph` that orchestrates a multi-agent workflow.
* :mod:`app.orchestrator.review` — :class:`HumanReviewQueue` for the
  HITL approval gate.
* :mod:`app.orchestrator.decision_boundary` —
  :class:`DecisionBoundaryMiddleware` (blast-radius calculation +
  policy gate).
"""

from __future__ import annotations

from app.orchestrator.agent import Agent, AgentResult, ToolCall
from app.orchestrator.decision_boundary import (
    ActionContext,
    DecisionBoundaryMiddleware,
)
from app.orchestrator.langgraph_flow import (
    WorkflowState,
    build_workflow,
    run_workflow,
)
from app.orchestrator.queue import TaskQueue
from app.orchestrator.review import HumanReviewQueue

__all__ = [
    "ActionContext",
    "Agent",
    "AgentResult",
    "DecisionBoundaryMiddleware",
    "HumanReviewQueue",
    "TaskQueue",
    "ToolCall",
    "WorkflowState",
    "build_workflow",
    "run_workflow",
]
"""Decision-boundary middleware — gates high-consequence agent actions.

This module implements the "Human Authority Preserved" principle from
the Phase 3 plan (Section 1). Before any tool call is allowed to
execute, the :class:`DecisionBoundaryMiddleware` evaluates:

1. **Principal policy** — is the requesting principal allowed to use
   this tool at all? (e.g., a ``readonly`` principal cannot invoke
   write tools).
2. **Blast radius** — what is the worst-case impact of this action?
   Computed from a per-tool ``estimate_blast_radius`` callable (or a
   default heuristic) and compared against a per-principal budget.
3. **Tool classification** — some tools are unconditionally sensitive
   (e.g., ``"shell"``, ``"file_delete"``, ``"jira.issue.delete"``)
   and always require review.

The middleware exposes two things:

* :class:`ActionContext` — a Pydantic model describing the action
  under consideration (principal, tool, args, etc.).
* :class:`DecisionBoundaryMiddleware` — the policy object. Its
  :meth:`evaluate` returns a :class:`Decision` describing what the
  orchestrator should do next (``allow``, ``review``, ``deny``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Severity

# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------


class Principal(BaseModel):
    """The entity on whose behalf an action is being taken.

    The Phase 3 plan calls out RBAC; this is the minimal surface
    needed by the middleware.
    """

    id: str = Field(..., description="Stable principal identifier.")
    roles: List[str] = Field(
        default_factory=list,
        description="Roles assigned to the principal.",
    )
    blast_radius_budget: int = Field(
        default=100,
        ge=0,
        description="Max blast-radius sum the principal may incur "
        "across a single task before a review is required.",
    )


class ActionContext(BaseModel):
    """Context for a single tool-call decision."""

    principal: Principal
    tool: str = Field(..., description="Name of the tool being called.")
    args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the tool.",
    )
    task_id: Optional[str] = Field(
        default=None,
        description="Optional task identifier (for audit logging).",
    )


class Decision(BaseModel):
    """Outcome of a decision-boundary evaluation."""

    allow: bool = Field(
        ...,
        description="True if the action may proceed without review.",
    )
    require_review: bool = Field(
        ...,
        description="True if the action must be queued for human review.",
    )
    severity: Severity = Field(
        default=Severity.LOW,
        description="Severity classification of the action.",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation.",
    )
    blast_radius: int = Field(
        default=0,
        description="Estimated blast radius (records affected, etc.).",
    )


# Type for a sync blast-radius estimator. Async estimators are also
# supported via :class:`AsyncBlastRadiusEstimator`.
BlastRadiusEstimator = Callable[[str, Dict[str, Any]], int]
AsyncBlastRadiusEstimator = Callable[[str, Dict[str, Any]], Awaitable[int]]


# Tools that are *always* sensitive regardless of arguments.
# These map to the "tool allowlist" / "argument validation" topics
# in the Phase 3 plan (Section 4.4).
_SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {
        # Generic primitives
        "shell",
        "exec",
        "subprocess",
        "file_delete",
        "file_write",
        "rm",
        # Common enterprise write tools
        "jira.issue.delete",
        "jira.issue.update",
        "github.merge",
        "github.repo.delete",
        "slack.message.post",
        "email.send",
        "ticket.create",
        # Database
        "db.write",
        "db.delete",
    }
)

# Default blast-radius estimate when no estimator is supplied.
# Heuristic: 1 record per "id"/"ids" arg, +100 for shell-like tools.
def _default_blast_radius(tool: str, args: Dict[str, Any]) -> int:
    if tool in _SENSITIVE_TOOLS:
        # Arbitrary shell / write actions — assume worst case.
        return 1000
    # Count IDs / record lists in the args.
    n = 0
    for key in ("id", "ids", "record_ids", "user_ids", "issue_ids"):
        v = args.get(key)
        if isinstance(v, str):
            n += 1
        elif isinstance(v, list):
            n += len(v)
    # Files / paths contribute 1 each.
    for key in ("path", "paths", "files"):
        v = args.get(key)
        if isinstance(v, str):
            n += 1
        elif isinstance(v, list):
            n += len(v)
    return max(1, n)


# ---------------------------------------------------------------------
# DecisionBoundaryMiddleware
# ---------------------------------------------------------------------


@dataclass
class DecisionBoundaryMiddleware:
    """Per-principal policy gate with blast-radius budgeting.

    Configuration:

    * ``sensitive_tools`` — set of tool names that always require
      review. Defaults to a conservative built-in list.
    * ``role_allowlists`` — ``role -> set(allowed_tools)``. A
      principal may only use tools in their roles' union.
    * ``role_blocklist`` — ``role -> set(forbidden_tools)``. Takes
      precedence over ``role_allowlists``.
    * ``blast_radius_estimator`` — synchronous estimator for the
      blast radius. Defaults to :func:`_default_blast_radius`.
    * ``async_blast_radius_estimator`` — async variant; used when
      supplied (e.g., to query the database for record counts).

    The middleware keeps a small per-principal ledger of the
    accumulated blast radius within a single task. Call
    :meth:`begin_task` at the start of a task and :meth:`end_task` at
    the end.
    """

    sensitive_tools: frozenset[str] = field(
        default_factory=lambda: _SENSITIVE_TOOLS,
    )
    role_allowlists: Dict[str, frozenset[str]] = field(default_factory=dict)
    role_blocklist: Dict[str, frozenset[str]] = field(default_factory=dict)
    blast_radius_estimator: BlastRadiusEstimator = field(
        default=_default_blast_radius,
    )
    async_blast_radius_estimator: Optional[AsyncBlastRadiusEstimator] = field(
        default=None,
    )

    # Per-task ledger: principal_id -> accumulated blast radius.
    _ledger: Dict[str, int] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Task-scoped ledger
    # ------------------------------------------------------------------
    def begin_task(self, principal_id: str) -> None:
        """Reset the blast-radius ledger for ``principal_id``."""
        self._ledger[principal_id] = 0

    def end_task(self, principal_id: str) -> None:
        """Clear the ledger entry for ``principal_id``."""
        self._ledger.pop(principal_id, None)

    # ------------------------------------------------------------------
    # Principal checks
    # ------------------------------------------------------------------
    def _allowed_for_principal(self, principal: Principal, tool: str) -> bool:
        if not principal.roles:
            # No roles at all -> only allow if there are no allowlists
            # configured (open system).
            return not self.role_allowlists
        # Blocklist takes precedence.
        for role in principal.roles:
            if tool in self.role_blocklist.get(role, frozenset()):
                return False
        if not self.role_allowlists:
            # No allowlists configured -> everything allowed (except
            # blocklist hits above).
            return True
        allowed: set[str] = set()
        for role in principal.roles:
            allowed.update(self.role_allowlists.get(role, frozenset()))
        return tool in allowed

    # ------------------------------------------------------------------
    # Blast-radius estimation
    # ------------------------------------------------------------------
    async def _estimate(self, tool: str, args: Dict[str, Any]) -> int:
        if self.async_blast_radius_estimator is not None:
            return int(await self.async_blast_radius_estimator(tool, args))
        return int(self.blast_radius_estimator(tool, args))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def evaluate(
        self,
        ctx: ActionContext,
    ) -> Decision:
        """Decide whether ``ctx`` may proceed, must be reviewed, or denied.

        Returns a :class:`Decision` with:

        * ``allow=True``, ``require_review=False`` — proceed.
        * ``allow=False``, ``require_review=True`` — gate for review.
        * ``allow=False``, ``require_review=False`` — denied (this
          happens when a tool is in the principal's blocklist, or when
          the accumulated blast radius exceeds the budget and the
          principal has no review role).
        """
        principal = ctx.principal
        tool = ctx.tool

        # 1. Principal allowlist / blocklist.
        if not self._allowed_for_principal(principal, tool):
            return Decision(
                allow=False,
                require_review=False,
                severity=Severity.HIGH,
                reason=f"principal {principal.id} not allowed to use tool {tool!r}",
                blast_radius=0,
            )

        # 2. Estimate blast radius.
        try:
            radius = await self._estimate(tool, ctx.args)
        except Exception as exc:  # noqa: BLE001
            # Estimators can fail (e.g., DB unreachable). Default to
            # a high-conservative radius so we err toward review.
            radius = 1000
            review_reason = (
                f"blast-radius estimator failed ({exc!r}); defaulting to review"
            )
        else:
            review_reason = ""

        # 3. Sensitive tools -> always review, regardless of radius.
        if tool in self.sensitive_tools:
            self._ledger[principal.id] = (
                self._ledger.get(principal.id, 0) + radius
            )
            return Decision(
                allow=False,
                require_review=True,
                severity=Severity.CRITICAL,
                reason=(
                    review_reason
                    or f"tool {tool!r} is sensitive (blast_radius={radius})"
                ),
                blast_radius=radius,
            )

        # 4. Per-task ledger check.
        accumulated = self._ledger.get(principal.id, 0) + radius
        if accumulated > principal.blast_radius_budget:
            # Over budget -> require review (don't deny — humans can
            # still approve).
            self._ledger[principal.id] = accumulated
            return Decision(
                allow=False,
                require_review=True,
                severity=Severity.HIGH,
                reason=(
                    f"accumulated blast_radius={accumulated} exceeds "
                    f"budget={principal.blast_radius_budget}"
                ),
                blast_radius=radius,
            )

        # 5. Default: allow.
        self._ledger[principal.id] = accumulated
        return Decision(
            allow=True,
            require_review=False,
            severity=Severity.LOW,
            reason="within budget",
            blast_radius=radius,
        )

    # ------------------------------------------------------------------
    # Helper used by Agent.should_request_human_review
    # ------------------------------------------------------------------
    def should_request_human_review(self, action: str) -> bool:
        """Quick, sync policy check used as a fast-path in :class:`Agent`.

        This is intentionally conservative — anything not whitelisted
        is treated as "needs review". For the full policy with
        blast-radius budgeting, use :meth:`evaluate`.
        """
        action_norm = (action or "").strip().lower()
        if not action_norm:
            return True
        if action_norm in self.sensitive_tools:
            return True
        # Conservative default: treat unknown actions as needing
        # review.  This aligns with the Phase 3 principle "human
        # authority preserved".
        return True


__all__ = [
    "ActionContext",
    "BlastRadiusEstimator",
    "AsyncBlastRadiusEstimator",
    "Decision",
    "DecisionBoundaryMiddleware",
    "Principal",
    "_default_blast_radius",
    "_SENSITIVE_TOOLS",
]
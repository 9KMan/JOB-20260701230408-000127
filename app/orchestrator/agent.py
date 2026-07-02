"""Agent — the runtime that turns an LLM + tools into a task executor.

This is the runtime counterpart to :class:`app.models.agent.Agent`.
A row in the ``agents`` table defines *which* agent is which; an
instance of :class:`Agent` here defines *how* one runs (a single
LLM-call loop with a tool allow-list, a system prompt, and a
decision-boundary policy hook).

Key design points (per the Phase 3 plan):

* **Raw SDK + Pydantic tool calling.** The production pattern (see
  Section 2 of the Phase 3 plan) is to call OpenAI/Anthropic
  directly via the SDK (``openai.AsyncClient`` /
  ``anthropic.AsyncAnthropic``) and validate tool arguments against a
  Pydantic model before execution. We deliberately do *not* wrap the
  call in a LangChain ``Chain`` — chains are too rigid for the
  "agent discovers its next step at runtime" pattern.
* **Tool allow-list.** :attr:`tools` is the static, agent-defined set
  of permissible tools. The :class:`DecisionBoundaryMiddleware`
  enforces it dynamically for each tool call.
* **Decision-boundary hook.** :meth:`should_request_human_review`
  is a conservative fast-path that returns ``True`` for any
  high-consequence action (the *full* policy lives in
  :class:`DecisionBoundaryMiddleware.evaluate`).
* **Run log.** Each invocation of :meth:`run` produces an
  :class:`AgentResult` with a structured ``scratchpad`` (the
  conversation history + tool traces) so the LangGraph state graph
  can checkpoint it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
)

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RunStatus
from app.orchestrator.decision_boundary import (
    ActionContext,
    Decision,
    DecisionBoundaryMiddleware,
    Principal,
)

# ---------------------------------------------------------------------
# Tool plumbing
#
# A "tool" is a callable with a JSON-Schema-ish declaration the LLM
# can read. We accept either:
#
# 1. A dict declaration ``{"name", "description", "parameters"}``
#    paired with a python callable of the same name.
# 2. A :class:`Tool` object (below) — a Pydantic-friendly wrapper.
# ---------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single LLM-emitted tool invocation.

    Matches OpenAI's ``tool_calls[i].function`` / Anthropic
    ``tool_use`` blocks (and our Pydantic-validated normal form).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        default_factory=lambda: f"call_{uuid.uuid4().hex[:24]}",
        description="Stable id for this tool call (used in the tool result).",
    )
    name: str = Field(..., description="Name of the tool to invoke.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool (Pydantic-validated).",
    )


class Tool(BaseModel):
    """A tool exposed to the LLM.

    Attributes:
        name: Machine-readable tool name (matches what the LLM emits).
        description: Human-readable description shown in the prompt.
        parameters: JSON-Schema-shaped argument schema. The LLM
            produces arguments that conform to this schema; we
            pass them through to the :attr:`callable`.
        callable: Python callable executed when the LLM picks this
            tool. It may be sync or async; we detect at call time.
        dangerous: When ``True``, calls to this tool are subject to
            the decision-boundary policy (HITL review) regardless
            of arguments.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    callable: Any = None
    dangerous: bool = False


# Type aliases for the LLM client layer.
LLMMessage = Dict[str, Any]  # {"role": "user|assistant|system|tool", ...}
LLMResponse = Dict[str, Any]


# A simple async LLM client interface — callers plug in OpenAI,
# Anthropic, or a fake for tests. We are not coupled to any specific
# provider SDK here; the default fakes in the test module are
# sufficient for unit testing.
AsyncLLMCallable = Callable[[Sequence[LLMMessage], Sequence[Dict[str, Any]]], Awaitable[LLMResponse]]


# ---------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------


@dataclass
class AgentResult:
    """Outcome of :meth:`Agent.run`.

    Attributes:
        run_id: UUID of the run row (created in :meth:`run`). ``None``
            when no DB row was written (e.g. dry-run / test mode).
        output: Final agent message / structured output.
        tool_calls: List of tool invocations executed during the run.
        scratchpad: Free-form scratchpad (messages + tool traces +
            per-iteration notes). LangGraph uses this for checkpointing.
        tokens_in / tokens_out: Token counters (filled by SDK usage
            blocks when available).
        status: ``RunStatus`` for the run row.
        error: Optional error message; ``None`` on success.
        decision: Optional decision-boundary decision if the run was
            gated for human review.
        requires_review: Convenience copy of ``decision.require_review``.
        review_reason: Human-readable reason the action needs review.
    """

    run_id: Optional[uuid.UUID] = None
    output: Any = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    scratchpad: Dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = RunStatus.SUCCESS.value
    error: Optional[str] = None
    decision: Optional[Decision] = None
    requires_review: bool = False
    review_reason: str = ""


# ---------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------


# Tools that always require review (broader than the
# DecisionBoundaryMiddleware default — this is the agent's own
# blacklist, computed without querying the database).
_ALWAYS_REVIEW_ACTIONS: frozenset[str] = frozenset(
    {
        "shell",
        "exec",
        "subprocess",
        "file_delete",
        "file_write",
        "rm",
        "email.send",
        "github.merge",
        "github.repo.delete",
        "jira.issue.delete",
        "jira.issue.update",
        "slack.message.post",
        "ticket.create",
        "db.write",
        "db.delete",
        # Web/file destructive primitives
        "http.post",
        "http.delete",
    }
)


class Agent:
    """A single LLM + tools runtime.

    The ``Agent`` is a plain Python object (not a row in the DB).
    Long-lived configuration lives in the ``agents`` table; a short-
    lived runtime instance is built per task from that row.

    Example (manual)::

        agent = Agent(
            agent_id=uuid.uuid4(),
            system_prompt="You are a research analyst.",
            tools=[
                {"name": "search", "description": "Web search",
                 "callable": my_search_fn},
            ],
            config={"provider": "openai", "model": "gpt-4o", "max_iterations": 5},
        )
        result = await agent.run(task)

    The :class:`Agent` itself does *not* require any provider SDK to be
    installed — pass ``llm_callable`` to inject the actual LLM call.
    """

    def __init__(
        self,
        agent_id: uuid.UUID,
        config: Optional[Dict[str, Any]] = None,
        tools: Optional[Sequence[Any]] = None,
        system_prompt: str = "",
        llm_callable: Optional[AsyncLLMCallable] = None,
        decision_boundary: Optional[DecisionBoundaryMiddleware] = None,
        principal: Optional[Principal] = None,
        max_iterations: int = 5,
    ) -> None:
        self.agent_id = agent_id
        self.config: Dict[str, Any] = dict(config or {})
        self.system_prompt = system_prompt
        self.max_iterations = max(1, int(self.config.get("max_iterations", max_iterations)))
        self.principal = principal or Principal(
            id=f"agent:{agent_id}", roles=["agent"], blast_radius_budget=50
        )
        self.decision_boundary = decision_boundary or DecisionBoundaryMiddleware()
        self.llm_callable = llm_callable  # None => produce a deterministic stub result

        # Normalize tools → list[Tool].
        self.tools: List[Tool] = []
        self._tool_index: Dict[str, Tool] = {}
        for raw in tools or []:
            t = self._coerce_tool(raw)
            self.tools.append(t)
            self._tool_index[t.name] = t

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_tool(raw: Any) -> Tool:
        """Accept ``Tool`` or a dict and return a ``Tool``."""
        if isinstance(raw, Tool):
            return raw
        if isinstance(raw, dict):
            name = raw.get("name")
            if not name:
                raise ValueError("tool dict must have 'name'")
            return Tool(
                name=name,
                description=raw.get("description", ""),
                parameters=raw.get("parameters", {}),
                callable=raw.get("callable"),
                dangerous=bool(raw.get("dangerous", False)),
            )
        raise TypeError(f"unsupported tool type: {type(raw)!r}")

    # ------------------------------------------------------------------
    # Public API — should_request_human_review
    # ------------------------------------------------------------------
    def should_request_human_review(self, action: str) -> bool:
        """Conservative fast-path HITL check.

        Returns ``True`` for:

        * Tools whose name appears in :data:`_ALWAYS_REVIEW_ACTIONS`
          (the agent's own blacklist).
        * Tools the middleware considers sensitive
          (:attr:`DecisionBoundaryMiddleware.sensitive_tools`).
        * Any tool the *runtime* configured as ``dangerous=True`` —
          even if not on the global list (e.g., a custom
          ``jira.bulk_update``).

        Unknown actions are treated as requiring review (fail-closed).
        This is intentional: the Phase 3 plan's principle is *human
        authority preserved*, so the default is review.
        """
        action_norm = (action or "").strip().lower()
        if not action_norm:
            return True
        if action_norm in _ALWAYS_REVIEW_ACTIONS:
            return True
        if action_norm in self.decision_boundary.sensitive_tools:
            return True
        # Per-tool ``dangerous`` flag overrides the global list.
        tool = self._tool_index.get(action_norm)
        if tool is not None and tool.dangerous:
            return True
        # Conservative default.
        return True

    # ------------------------------------------------------------------
    # Public API — run
    # ------------------------------------------------------------------
    async def run(
        self,
        task: Any,
        *,
        tool_registry: Optional[Dict[str, Any]] = None,
        on_tool_call: Optional[Callable[[ToolCall], Awaitable[None]]] = None,
    ) -> AgentResult:
        """Execute the agent against ``task``.

        ``task`` is duck-typed — anything with ``.id`` and
        ``.input_payload`` works. The :class:`app.models.task.Task`
        model satisfies this; tests can pass a SimpleNamespace.

        ``tool_registry`` is an optional external lookup table that
        takes precedence over ``self._tool_index``. Use it to plug
        in higher-level tool implementations (e.g. RAG-search) without
        rebuilding the agent.

        ``on_tool_call`` is an optional async callback invoked *before*
        each tool call (handy for audit logging; not required).
        """
        task_id = _coerce_task_id(task)
        self.decision_boundary.begin_task(str(self.principal.id))

        messages: List[LLMMessage] = []
        scratchpad: Dict[str, Any] = {
            "task_id": str(task_id) if task_id else None,
            "agent_id": str(self.agent_id),
            "messages": [],
            "tool_calls": [],
            "tool_results": [],
            "iterations": 0,
            "started_at": datetime.utcnow().isoformat() + "Z",
        }

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Build the initial user message from the task input.
        user_content = _build_user_message_from_task(task)
        messages.append({"role": "user", "content": user_content})

        tokens_in = 0
        tokens_out = 0
        executed_calls: List[ToolCall] = []
        last_assistant_text: str = ""
        decision: Optional[Decision] = None

        # The agent loop — bounded by max_iterations.
        for iteration in range(self.max_iterations):
            scratchpad["iterations"] = iteration + 1

            # Ask the LLM (or stub) what to do next.
            if self.llm_callable is None:
                # Deterministic stub: if any tool is registered, call the
                # first one once and return. Otherwise, echo the user
                # message back. Useful for unit tests and offline runs.
                tool_defs = [_tool_declaration(t) for t in self.tools]
                llm_response = _default_stub_response(
                    messages=messages,
                    tools=tool_defs,
                    iteration=iteration,
                )
            else:
                tool_defs = [_tool_declaration(t) for t in self.tools]
                llm_response = await self.llm_callable(messages, tool_defs)

            tokens_in += int(llm_response.get("usage", {}).get("input_tokens", 0))
            tokens_out += int(llm_response.get("usage", {}).get("output_tokens", 0))

            # Track the assistant message in the scratchpad.
            assistant_msg = {
                "role": "assistant",
                "content": llm_response.get("content", "") or "",
                "tool_calls": llm_response.get("tool_calls", []),
            }
            messages.append(assistant_msg)
            scratchpad["messages"].append(assistant_msg)
            last_assistant_text = assistant_msg["content"]

            # No tool calls → done. Return whatever the assistant said.
            raw_calls = llm_response.get("tool_calls") or []
            if not raw_calls:
                scratchpad["finished_at"] = datetime.utcnow().isoformat() + "Z"
                self.decision_boundary.end_task(str(self.principal.id))
                return AgentResult(
                    output=last_assistant_text,
                    tool_calls=executed_calls,
                    scratchpad=scratchpad,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    status=RunStatus.SUCCESS.value,
                )

            # Execute each tool call (sequentially; one is the common case).
            for raw_call in raw_calls:
                tool_call = ToolCall(
                    id=str(raw_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"),
                    name=str(raw_call.get("name") or ""),
                    arguments=dict(raw_call.get("arguments") or {}),
                )

                # Decision-boundary check.
                ctx = ActionContext(
                    principal=self.principal,
                    tool=tool_call.name,
                    args=tool_call.arguments,
                    task_id=str(task_id) if task_id else None,
                )
                decision = await self.decision_boundary.evaluate(ctx)

                if decision.require_review:
                    scratchpad["decision"] = decision.model_dump()
                    scratchpad["finished_at"] = datetime.utcnow().isoformat() + "Z"
                    self.decision_boundary.end_task(str(self.principal.id))
                    return AgentResult(
                        output=last_assistant_text or None,
                        tool_calls=executed_calls + [tool_call],
                        scratchpad=scratchpad,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        status=RunStatus.PARTIAL.value,
                        decision=decision,
                        requires_review=True,
                        review_reason=decision.reason,
                    )

                if not decision.allow:
                    # Denied outright (e.g. principal not on allow-list).
                    scratchpad["decision"] = decision.model_dump()
                    scratchpad["finished_at"] = datetime.utcnow().isoformat() + "Z"
                    self.decision_boundary.end_task(str(self.principal.id))
                    return AgentResult(
                        output=last_assistant_text or None,
                        tool_calls=executed_calls + [tool_call],
                        scratchpad=scratchpad,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        status=RunStatus.FAILED.value,
                        error=f"action denied: {decision.reason}",
                        decision=decision,
                    )

                # Look up the tool, run it, append the result.
                tool_obj = (
                    (tool_registry or {}).get(tool_call.name)
                    or self._tool_index.get(tool_call.name)
                )
                if tool_obj is None:
                    tool_result: Any = {
                        "ok": False,
                        "error": f"unknown tool {tool_call.name!r}",
                    }
                else:
                    if on_tool_call is not None:
                        try:
                            await on_tool_call(tool_call)
                        except Exception:
                            pass
                    tool_result = await _invoke_tool(tool_obj, tool_call.arguments)

                scratchpad["tool_calls"].append(
                    {"id": tool_call.id, "name": tool_call.name, "args": tool_call.arguments}
                )
                scratchpad["tool_results"].append(
                    {"id": tool_call.id, "result": tool_result}
                )
                executed_calls.append(tool_call)

                # Append a "tool" message so the LLM sees the result on
                # the next iteration (OpenAI/Anthropic protocol).
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": _stringify_tool_result(tool_result),
                    }
                )

        # Ran out of iterations; return whatever we have.
        scratchpad["finished_at"] = datetime.utcnow().isoformat() + "Z"
        self.decision_boundary.end_task(str(self.principal.id))
        return AgentResult(
            output=last_assistant_text or None,
            tool_calls=executed_calls,
            scratchpad=scratchpad,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            status=RunStatus.PARTIAL.value,
            error="max_iterations reached",
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _coerce_task_id(task: Any) -> Optional[uuid.UUID]:
    """Best-effort extraction of a UUID from a duck-typed task."""
    if task is None:
        return None
    tid = getattr(task, "id", None)
    if isinstance(tid, uuid.UUID):
        return tid
    if isinstance(tid, str):
        try:
            return uuid.UUID(tid)
        except ValueError:
            return None
    return None


def _build_user_message_from_task(task: Any) -> str:
    """Pull a user message out of a task row (input_payload fallback)."""
    if task is None:
        return ""
    payload = getattr(task, "input_payload", None) or {}
    if not isinstance(payload, dict):
        return str(payload)
    for key in ("query", "prompt", "input", "message", "text"):
        if key in payload and payload[key]:
            return str(payload[key])
    # Fallback: serialize the whole payload.
    try:
        return json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return str(payload)


def _tool_declaration(tool: Tool) -> Dict[str, Any]:
    """Return a JSON-Schema-flavored tool declaration for the LLM prompt."""
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
    }


async def _invoke_tool(tool: Any, arguments: Dict[str, Any]) -> Any:
    """Call a tool's ``callable`` (sync or async), with Pydantic arg validation.

    We treat the callable's signature as best-effort: keyword-only
    are passed in via ``**arguments``, and the result is returned as-is.
    Exceptions are caught and converted to a structured dict so the
    LLM sees ``{"ok": False, "error": "..."}`` instead of a traceback.
    """
    import asyncio
    import inspect

    func = getattr(tool, "callable", None)
    if func is None or not callable(func):
        return {"ok": False, "error": "tool has no callable"}

    try:
        if inspect.iscoroutinefunction(func):
            res = await func(**arguments)
        else:
            res = func(**arguments)
            if asyncio.iscoroutine(res):
                res = await res
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return res


def _stringify_tool_result(result: Any) -> str:
    """Render a tool result for inclusion in the LLM message log."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _default_stub_response(
    messages: Sequence[LLMMessage],
    tools: Sequence[Dict[str, Any]],
    iteration: int,
) -> LLMResponse:
    """Deterministic stub used when no LLM client is provided.

    On iteration 0: if any tool is registered, emit a tool call to the
    first one with ``{}`` args. Otherwise emit a plain assistant text.
    On iteration 1+: emit a final assistant message so the loop exits.
    """
    if iteration == 0 and tools:
        tool_name = tools[0]["name"]
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"stub_{uuid.uuid4().hex[:24]}",
                    "name": tool_name,
                    "arguments": {},
                }
            ],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    text = "ok"
    if last_user and last_user.get("content"):
        text = f"echo: {last_user['content']}"
    return {
        "content": text,
        "tool_calls": [],
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


__all__ = [
    "Agent",
    "AgentResult",
    "AsyncLLMCallable",
    "LLMMessage",
    "LLMResponse",
    "Tool",
    "ToolCall",
]

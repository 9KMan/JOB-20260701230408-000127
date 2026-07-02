"""Agent ORM model — registered AI agent configuration.

Stores the static configuration for an agent: its role, LLM provider
settings, system prompt, tool allow-list, and arbitrary extra config.

The runtime ``Agent`` instance (in ``app/orchestrator/agent.py``)
loads one of these rows to construct itself.
"""

from __future__ import annotations

import uuid
from typing import Any, List

from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentRole


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered autonomous agent.

    Attributes:
        id: UUID PK (separate from the runtime ``agent_id`` string
            used in logs and queues — the UUID is the DB key).
        name: Human-readable agent name (unique lookup key).
        role: ``AgentRole`` value, stored as string.
        config: Free-form JSON config (provider, model, temperature,
            max_tokens, etc.). The runtime ``Agent`` reads this to
            configure itself.
        system_prompt: System message prepended to every LLM call.
        tools: JSONB list of tool names the agent is allowed to
            invoke. Enforced by the decision-boundary middleware.
        created_at / updated_at: From ``TimestampMixin``.
    """

    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AgentRole.CUSTOM.value,
        server_default=text(f"'{AgentRole.CUSTOM.value}'"),
        index=True,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    tools: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    __table_args__ = (
        Index("ix_agents_role_created_at", "role", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Agent id={self.id} name={self.name} role={self.role}>"


__all__ = ["Agent"]
## Phase Goal
Define the complete data model with entity schemas, relationships, migration scaffolding, and storage abstractions for PostgreSQL + pgvector that support agent orchestration, RAG, memory, evaluation, and governance.

## Files to Create

```file:src/models/__init__.py
"""Data models package — exports all ORM models, schemas, and enums."""

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import (
    AgentRole,
    AgentStatus,
    TaskStatus,
    MessageRole,
    DocumentStatus,
    MemoryType,
    ApprovalStatus,
    EvaluationStatus,
)
from src.models.agent import Agent, AgentCapability
from src.models.task import Task, TaskDependency, TaskArtifact
from src.models.conversation import Conversation, Message
from src.models.document import Document, DocumentChunk
from src.models.memory import MemoryEntry
from src.models.approval import ApprovalRequest, ApprovalDecision
from src.models.evaluation import EvaluationRun, EvaluationResult, EvaluationMetric
from src.models.audit import AuditLog
from src.models.checkpoint import AgentCheckpoint

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "AgentRole",
    "AgentStatus",
    "TaskStatus",
    "MessageRole",
    "DocumentStatus",
    "MemoryType",
    "ApprovalStatus",
    "EvaluationStatus",
    "Agent",
    "AgentCapability",
    "Task",
    "TaskDependency",
    "TaskArtifact",
    "Conversation",
    "Message",
    "Document",
    "DocumentChunk",
    "MemoryEntry",
    "ApprovalRequest",
    "ApprovalDecision",
    "EvaluationRun",
    "EvaluationResult",
    "EvaluationMetric",
    "AuditLog",
    "AgentCheckpoint",
]
```

```file:src/models/base.py
"""SQLAlchemy declarative base with common mixins."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""

    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
    }


class TimestampMixin:
    """Adds created_at and updated_at columns with auto-management."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """UUID primary key column, generated server-side."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
```

```file:src/models/enums.py
"""Enumerations used across the data model."""

from __future__ import annotations

import enum


class AgentRole(str, enum.Enum):
    """Role of an agent within the multi-agent system."""

    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"
    CUSTOM = "custom"


class AgentStatus(str, enum.Enum):
    """Lifecycle status of an agent instance."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class TaskStatus(str, enum.Enum):
    """Lifecycle status of an orchestrated task."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageRole(str, enum.Enum):
    """Role of a message in a conversation thread."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class DocumentStatus(str, enum.Enum):
    """Processing status of an ingested document."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    ARCHIVED = "archived"


class MemoryType(str, enum.Enum):
    """Classification of AI memory entries."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class ApprovalStatus(str, enum.Enum):
    """Status of a human-in-the-loop approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class EvaluationStatus(str, enum.Enum):
    """Status of an evaluation run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

```file:src/models/agent.py
"""Agent and AgentCapability ORM models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import AgentRole, AgentStatus

if TYPE_CHECKING:
    from src.models.task import Task
    from src.models.checkpoint import AgentCheckpoint


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered autonomous AI agent in the orchestration system."""

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_agents_name_version"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    role: Mapped[AgentRole] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        default=AgentRole.CUSTOM,
    )
    status: Mapped[AgentStatus] = mapped_column(
        String(32),
        nullable=False,
        default=AgentStatus.ACTIVE,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(default=0.0, nullable=False)
    max_tokens: Mapped[int] = mapped_column(default=4096, nullable=False)
    tools: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    capabilities: Mapped[List["AgentCapability"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="assigned_agent")
    checkpoints: Mapped[List["AgentCheckpoint"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Agent {self.name} v{self.version} role={self.role}>"


class AgentCapability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A discrete capability exposed by an agent (used for routing/delgation)."""

    __tablename__ = "agent_capabilities"
    __table_args__ = (
        UniqueConstraint("agent_id", "capability_key", name="uq_agent_capability"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)

    agent: Mapped["Agent"] = relationship(back_populates="capabilities")

    def __repr__(self) -> str:
        return f"<AgentCapability {self.capability_key} agent={self.agent_id}>"
```

```file:src/models/task.py
"""Task, TaskDependency, TaskArtifact ORM models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import TaskStatus

if TYPE_CHECKING:
    from src.models.agent import Agent
    from src.models.approval import ApprovalRequest


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A unit of work delegated to (or by) an agent."""

    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False, index=True)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    assigned_agent: Mapped[Optional["Agent"]] = relationship(back_populates="tasks")
    dependencies: Mapped[List["TaskDependency"]] = relationship(
        back_populates="task",
        foreign_keys="TaskDependency.task_id",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[List["TaskArtifact"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    approval_requests: Mapped[List["ApprovalRequest"]] = relationship(back_populates="task")

    def __repr__(self) -> str:
        return f"<Task {self.title} status={self.status}>"


class TaskDependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Directed edge expressing that one task depends on another."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    required: Mapped[bool] = mapped_column(default=True, nullable=False)

    task: Mapped["Task"] = relationship(foreign_keys=[task_id], back_populates="dependencies")

    def __repr__(self) -> str:
        return f"<TaskDependency {self.task_id} -> {self.depends_on_task_id}>"


from sqlalchemy import UniqueConstraint  # noqa: E402  (needed for __table_args__)


class TaskArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A file or structured artifact produced by a task."""

    __tablename__ = "task_artifacts"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<TaskArtifact {self.name} type={self.artifact_type}>"
```

```file:src/models/conversation.py
"""Conversation and Message ORM models for agent communication."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import MessageRole

if TYPE_CHECKING:
    from src.models.agent import Agent


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A thread of messages between user(s), agents, and tools."""

    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    participant_agent_ids: Mapped[List[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        default=list,
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sequence_number",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} messages={len(self.messages)}>"


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single message within a conversation."""

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        String(32),
        nullable=False,
        default=MessageRole.USER,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender_agent: Mapped[Optional["Agent"]] = relationship()

    def __repr__(self) -> str:
        return f"<Message {self.id} role={self.role} seq={self.sequence_number}>"
```

```file:src/models/document.py
"""Document and DocumentChunk ORM models (with pgvector embeddings)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import DocumentStatus

if TYPE_CHECKING:
    pass


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A source document ingested into the RAG pipeline."""

    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    collection: Mapped[str] = mapped_column(String(128), default="default", nullable=False, index=True)
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tsv: Mapped[object] = mapped_column(TSVECTOR, nullable=True)

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )

    def __repr__(self) -> str:
        return f"<Document {self.title} status={self.status}>"


from sqlalchemy import JSON  # noqa: E402  (re-export safe)


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chunked segment of a document with its vector embedding."""

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list] = mapped_column(
        Vector(dim=1536),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk doc={self.document_id} idx={self.chunk_index}>"
```

```file:src/models/memory.py
"""MemoryEntry ORM model for persistent AI memory."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.enums import MemoryType
from sqlalchemy import JSON
from pgvector.sqlalchemy import Vector


class MemoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A persistent memory entry stored across sessions."""

    __tablename__ = "memory_entries"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    memory_type: Mapped[MemoryType] = mapped_column(
        String(32),
        nullable=False,
        default=MemoryType.LONG_TERM,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
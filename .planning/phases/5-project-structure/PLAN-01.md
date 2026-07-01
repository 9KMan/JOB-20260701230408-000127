## Phase Goal
Establish the complete directory layout, module boundaries, and file organization for the AI agentic platform, creating a production-ready Python project skeleton with proper packaging, separation of concerns, and discoverable entry points for all subsystems.

## Files to Create

```file:pyproject.toml
[build-system]
requires = ["setuptools>=68.0", "wheel", "setuptools_scm[toml]>=7.0"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-agentic-platform"
version = "0.1.0"
description = "Enterprise AI agentic platform with multi-agent orchestration, RAG, and governance"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Proprietary" }
authors = [
    { name = "AI Systems Engineering", email = "[email protected]" },
]
keywords = ["ai-agents", "multi-agent", "rag", "langgraph", "mcp", "enterprise-ai"]

dependencies = [
    # Core LLM and agent framework
    "langchain>=0.2.0",
    "langchain-core>=0.2.0",
    "langgraph>=0.2.0",
    "langchain-openai>=0.1.0",
    "langchain-anthropic>=0.1.0",
    "langchain-community>=0.2.0",

    # API layer
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "python-multipart>=0.0.9",

    # Database and vector search
    "sqlalchemy>=2.0.30",
    "asyncpg>=0.29.0",
    "psycopg[binary]>=3.1.0",
    "pgvector>=0.3.0",
    "alembic>=1.13.0",

    # MCP (Model Context Protocol)
    "mcp>=1.0.0",

    # Observability and evaluation
    "langsmith>=0.1.0",
    "structlog>=24.1.0",
    "opentelemetry-api>=1.25.0",
    "opentelemetry-sdk>=1.25.0",
    "opentelemetry-instrumentation-fastapi>=0.46b0",

    # Resilience and utilities
    "tenacity>=8.3.0",
    "httpx>=0.27.0",
    "orjson>=3.10.0",

    # Security
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.5.0",
    "mypy>=1.10.0",
    "pre-commit>=3.7.0",
    "ipython>=8.25.0",
]
test = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "respx>=0.21.0",
]

[project.urls]
Documentation = "https://docs.example.internal/ai-platform"
Source = "https://git.example.internal/ai-agentic-platform"

[project.scripts]
ai-platform = "ai_platform.cli:main"
ai-platform-api = "ai_platform.api.app:run"

[tool.setuptools.packages.find]
where = ["src"]
include = ["ai_platform*"]

[tool.setuptools.package-data]
ai_platform = ["py.typed", "migrations/*.sql"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF", "ASYNC", "S", "TCH"]
ignore = ["S101", "E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101", "S106", "S105"]
"src/ai_platform/**/__init__.py" = ["F401"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
no_implicit_optional = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = [
    "langchain.*",
    "langgraph.*",
    "mcp.*",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--cov=src/ai_platform",
    "--cov-report=term-missing",
    "--cov-report=html",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]

[tool.coverage.run]
branch = true
source = ["src/ai_platform"]
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/migrations/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
show_missing = true
fail_under = 70
```

```file:src/ai_platform/__init__.py
"""AI Agentic Platform - Enterprise multi-agent orchestration with RAG and governance."""

from ai_platform.__version__ import __version__

__all__ = ["__version__"]
```

```file:src/ai_platform/__version__.py
"""Version information."""

__version__ = "0.1.0"
```

```file:src/ai_platform/py.typed
# Marker file for PEP 561 - package ships inline type hints
```

```file:src/ai_platform/config.py
"""Centralized configuration management using Pydantic Settings.

Loads configuration from environment variables and .env files with strong typing.
All subsystems should import settings from here rather than reading os.environ directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Database
    database_url: PostgresDsn
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # Vector search
    vector_index_type: Literal["hnsw", "ivfflat"] = "hnsw"
    vector_hnsw_m: int = 16
    vector_hnsw_ef_construction: int = 64
    vector_hnsw_ef_search: int = 40
    vector_target_recall_ms: int = 100

    # LLM providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    default_llm_provider: Literal["openai", "anthropic"] = "openai"
    default_llm_model: str = "gpt-4o"
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 60.0

    # LangSmith / observability
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "ai-agentic-platform"
    otel_exporter_otlp_endpoint: str | None = None

    # MCP
    mcp_server_enabled: bool = True
    mcp_server_name: str = "ai-platform-mcp"

    # Security
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    api_key_header: str = "X-API-Key"

    # Agent runtime
    agent_max_iterations: int = 25
    agent_recursion_limit: int = 50
    human_approval_timeout_seconds: int = 300

    # Paths
    project_root: Path = Path(__file__).resolve().parents[2]
    artifacts_dir: Path = Path("/var/lib/ai-platform/artifacts")

    @field_validator("artifacts_dir", mode="after")
    @classmethod
    def ensure_artifacts_dir(cls, v: Path) -> Path:
        """Create artifacts directory if it doesn't exist (best-effort)."""
        try:
            v.mkdir(parents=True, exist_ok=True)
        except OSError:
            # In test environments without write access, fall back to tmp
            import tempfile

            fallback = Path(tempfile.gettempdir()) / "ai-platform-artifacts"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance (singleton)."""
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    """Clear the settings cache (useful for tests)."""
    get_settings.cache_clear()
```

```file:src/ai_platform/logging_config.py
"""Structured logging configuration using structlog with OpenTelemetry integration."""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from ai_platform.config import Settings, get_settings


def add_app_context(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Inject application-level context into every log record."""
    settings = get_settings()
    event_dict.setdefault("environment", settings.environment)
    event_dict.setdefault("service", "ai-agentic-platform")
    return event_dict


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structured logging for the entire application."""
    settings = settings or get_settings()

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_app_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        # JSON for production log aggregation
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Human-readable for development
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge standard logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, settings.log_level),
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structured logger."""
    return structlog.get_logger(name)
```

```file:src/ai_platform/agents/__init__.py
"""Multi-agent orchestration module.

Contains LangGraph-based agent implementations, state management,
and coordination patterns for multi-agent systems.
"""
from ai_platform.agents.base import AgentProtocol, BaseAgent
from ai_platform.agents.state import AgentState, SharedState

__all__ = ["AgentProtocol", "BaseAgent", "AgentState", "SharedState"]
```

```file:src/ai_platform/agents/base.py
"""Base agent abstractions and protocols.

Defines the contract every agent implementation must satisfy.
Uses Protocol for structural typing — no inheritance required.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from ai_platform.agents.state import AgentState


@runtime_checkable
class AgentProtocol(Protocol):
    """Structural protocol every agent must satisfy."""

    name: str
    description: str

    @abstractmethod
    async def ainvoke(self, state: AgentState) -> AgentState:
        """Run the agent on the given state and return the updated state."""
        ...

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        """Return the tools this agent can invoke."""
        ...


class BaseAgent:
    """Concrete base class providing shared functionality.

    Subclasses should override _build_llm() and _build_tools().
    """

    def __init__(
        self,
        name: str,
        description: str,
        llm: BaseChatModel | None = None,
        tools: list[BaseTool] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._llm = llm or self._build_llm()
        self._tools = tools or self._build_tools()

    def _build_llm(self) -> BaseChatModel:
        """Override to provide a custom LLM instance."""
        raise NotImplementedError

    def _build_tools(self) -> list[BaseTool]:
        """Override to provide custom tools. Default: no tools."""
        return []

    def get_tools(self) -> list[BaseTool]:
        return list(self._tools)

    async def ainvoke(self, state: AgentState) -> AgentState:
        """Default invoke: bind tools to LLM and invoke."""
        if not self._tools:
            response = await self._llm.ainvoke(state.messages)
        else:
            llm_with_tools = self._llm.bind_tools(self._tools)
            response = await llm_with_tools.ainvoke(state.messages)
        return state.with_message(response)
```

```file:src/ai_platform/agents/state.py
"""Shared agent state definitions.

Uses TypedDict-compatible Pydantic models for LangGraph StateGraph compatibility
while providing type safety and serialization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class AgentState(BaseModel):
    """Mutable state passed between agent nodes in a LangGraph.

    The `messages` field uses LangGraph's add_messages reducer so that
    parallel branches correctly merge without losing messages.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: UUID = Field(default_factory=uuid4)
    run_id: UUID = Field(default_factory=uuid4)
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    next_agent: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    pending_approval: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def with_message(self, message: BaseMessage) -> AgentState:
        """Return a new state with the given message appended."""
        return self.model_copy(
            update={
                "messages": [*self.messages, message],
                "updated_at": datetime.now(timezone.utc),
            }
        )


class SharedState(BaseModel):
    """Cross-agent shared state for multi-agent coordination.

    Held in the orchestrator's checkpointer and broadcast to agents
    that subscribe to the shared context.
    """

    session_id: UUID = Field(default_factory=uuid4)
    participants: list[str] = Field(default_factory=list)
    blackboard: dict[str, Any] = Field(default_factory=dict)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    version: int = 0

    def write(self, key: str, value: Any, writer: str) -> None:
        """Atomic write to the blackboard with provenance."""
        self.blackboard[key] = {"value": value, "writer": writer, "version": self.version + 1}
        self.version += 1
```

```file:src/ai_platform/agents/orchestrator.py
"""Multi-agent orchestrator using LangGraph StateGraph.

Coordinates work across autonomous AI agents with conditional routing,
checkpointing, and human-in-the-loop interrupt points.
"""
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_platform.agents.base import AgentProtocol
from ai_platform.agents.state import AgentState


class AgentOrchestrator:
    """Coordinates multiple agents via a LangGraph StateGraph.

    The orchestrator owns the topology: which agent runs next depends on
    the `next_agent` field in state, set by each agent's output.
    """

    def __init__(
        self,
        agents: list[AgentProtocol],
        checkpointer: BaseCheckpointSaver | None = None,
        interrupt_before: list[str] | None = None,
    ) -> None:
        self.agents: dict[str, AgentProtocol] = {a.name: a for a in agents}
        self.checkpointer = checkpointer
        self.interrupt_before = interrupt_before or []
        self._graph: CompiledStateGraph[Any] = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph[Any]:
        """Construct the StateGraph with agent nodes and conditional edges."""
        graph: StateGraph[AgentState] = StateGraph(AgentState)

        for agent in self.agents.values():
            graph.add_node(agent.name, agent.ainvoke)

        graph.set_entry_point(self._select_initial_agent())

        for agent_name in self.agents:
            graph.add_conditional_edges(
                agent_name,
                self._route_next,
                {**{name: name for name in self.agents}, END: END},
            )

        return graph.compile(
            checkpointer=self.checkpointer,
            interrupt_before=self.interrupt_before,
        )

    def _select_initial_agent(self) -> str:
        """Default to the first registered agent."""
        return next(iter(self.agents))

    def _route_next(self, state: AgentState) -> str:
        """Decide which agent runs next based on state.next_agent."""
        if state.next_agent and state.next_agent in self.agents:
            return state.next_agent
        return END

    async def ainvoke(
        self,
        state: AgentState,
        config: dict[str, Any] | None = None,
    ) -> AgentState:
        """Run the orchestrator on an initial state."""
        result = await self._graph.ainvoke(state, config=config or {})
        return AgentState.model_validate(result)
```

```file:src/ai_platform/agents/__main__.py
"""Module entry point for running an agent standalone.

Usage: python -m ai_platform.agents
"""
from ai_platform.logging_config import configure_logging
from ai_platform.logging_config import get_logger as get_log

logger = get_log(__name__)


def main() -> None:
    configure_logging()
    logger.info("agents_module_loaded", status="ok")


if __name__ == "__main__":
    main()
```

```file:src/ai_platform/rag/__init__.py
"""Retrieval-Augmented Generation module.

Vector search, document ingestion, and semantic retrieval pipelines
backed by PostgreSQL with the pgvector extension.
"""
from ai_platform.rag.retriever import BaseRetriever, VectorRetriever
from ai_platform.rag.ingestion import DocumentIngester

__all__ = ["BaseRetriever", "VectorRetriever", "DocumentIngester"]
```

```file:src/ai_platform/rag/retriever.py
"""Vector retrieval abstractions over PostgreSQL + pgvector."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class RetrievalResult(BaseModel):
    """A single retrieval hit."""

    document_id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseRetriever(ABC):
    """Abstract base for all retrievers."""

    @abstractmethod
    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Return top-k most relevant documents for the query."""
        ...


class VectorRetriever(BaseRetriever):
    """Concrete retriever using pgvector with HNSW indexing.

    Targets <100ms query latency by tuning ef_search and HNSW parameters.
    """

    def __init__(
        self,
        connection_url: str,
        embedding_dim: int = 1536,
        ef_search: int = 40,
        hnsw_m: int = 16,
    ) -> None:
        self.connection_url = connection_url
        self.embedding_dim = embedding_dim
        self.ef_search = ef_search
        self.hnsw_m = hnsw_m

    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """Embed query and search pgvector index.

        Concrete implementation lives in Phase 7 (RAG implementation).
        This stub defines the contract.
        """
        raise NotImplementedError(
            "VectorRetriever.aretrieve will be implemented in the RAG phase"
        )
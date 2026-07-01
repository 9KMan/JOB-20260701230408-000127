## Phase Goal
Select and justify the complete technology stack by producing concrete dependency manifests, configuration files, and verification scripts that pin versions and prove the stack installs cleanly.

## Files to Create
```file:phase-2-stack/pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agentic-ai-platform"
version = "0.2.0"
description = "Enterprise AI platform: multi-agent orchestration, RAG, and HITL"
requires-python = ">=3.11"
authors = [{ name = "AI Systems Engineering" }]

# --- Core orchestration (LangGraph) ---
dependencies = [
  # LangGraph: graph-native agent orchestration with cycles + checkpointing
  "langgraph>=0.2.50,<0.3",
  "langgraph-checkpoint>=2.0,<3.0",
  "langgraph-checkpoint-postgres>=2.0,<3.0",

  # LangChain core + community providers
  "langchain-core>=0.3.0,<0.4",
  "langchain>=0.3.0,<0.4",
  "langchain-community>=0.3.0,<0.4",
  "langchain-openai>=0.2.0,<0.3",
  "langchain-anthropic>=0.2.0,<0.3",
  "langchain-postgres>=0.0.12,<0.1",

  # LLM provider SDKs (escape hatches for raw calls)
  "openai>=1.50.0,<2.0",
  "anthropic>=0.36.0,<1.0",

  # MCP (Model Context Protocol) for inter-agent tool protocol
  "mcp>=1.0.0,<2.0",
]

# --- Persistence: PostgreSQL + pgvector ---
dependencies += [
  "sqlalchemy>=2.0.30,<3.0",
  "psycopg[binary,pool]>=3.2.0,<4.0",
  "alembic>=1.13.0,<2.0",
  "pgvector>=0.3.6,<0.4",
]

# --- API layer: FastAPI + Pydantic v2 ---
dependencies += [
  "fastapi>=0.115.0,<1.0",
  "uvicorn[standard]>=0.32.0,<1.0",
  "pydantic>=2.9.0,<3.0",
  "pydantic-settings>=2.5.0,<3.0",
  "httpx>=0.27.0,<1.0",
]

# --- Observability & evaluation ---
dependencies += [
  "langfuse>=2.45.0,<3.0",
  "opentelemetry-api>=1.27.0,<2.0",
  "opentelemetry-sdk>=1.27.0,<2.0",
  "opentelemetry-instrumentation-fastapi>=0.48b0,<1.0",
  "prometheus-client>=0.21.0,<1.0",
  "pytest>=8.3.0,<9.0",
  "pytest-asyncio>=0.24.0,<1.0",
]

# --- Auth / governance ---
dependencies += [
  "python-jose[cryptography]>=3.3.0,<4.0",
  "passlib[bcrypt]>=1.7.4,<2.0",
]

[project.optional-dependencies]
dev = [
  "ruff>=0.7.0,<1.0",
  "mypy>=1.13.0,<2.0",
  "pytest-cov>=5.0.0,<6.0",
]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

```file:phase-2-stack/requirements.txt
# Pinned for reproducible installs in CI/CD
langgraph==0.2.50
langgraph-checkpoint==2.0.10
langgraph-checkpoint-postgres==2.0.10
langchain-core==0.3.21
langchain==0.3.7
langchain-community==0.3.7
langchain-openai==0.2.6
langchain-anthropic==0.2.6
langchain-postgres==0.0.12
openai==1.54.3
anthropic==0.36.2
mcp==1.0.0
sqlalchemy==2.0.36
psycopg[binary,pool]==3.2.3
alembic==1.13.3
pgvector==0.3.6
fastapi==0.115.4
uvicorn[standard]==0.32.0
pydantic==2.9.2
pydantic-settings==2.6.0
httpx==0.27.2
langfuse==2.45.2
opentelemetry-api==1.27.0
opentelemetry-sdk==1.27.0
opentelemetry-instrumentation-fastapi==0.48b0
prometheus-client==0.21.0
pytest==8.3.3
pytest-asyncio==0.24.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
```

```file:phase-2-stack/.env.example
# LLM Providers
OPENAI_API_KEY=sk-replace-me
ANTHROPIC_API_KEY=sk-ant-replace-me

# Database (PostgreSQL + pgvector)
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/agentic
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Vector search
VECTOR_DIM=1536
VECTOR_INDEX_TYPE=hnsw
VECTOR_EF_CONSTRUCTION=64
VECTOR_M=16

# Observability
LANGFUSE_PUBLIC_KEY=pk-replace-me
LANGFUSE_SECRET_KEY=sk-replace-me
LANGFUSE_HOST=https://cloud.langfuse.com

# Auth / Governance
JWT_SECRET=replace-me-32-bytes-min
JWT_ALGORITHM=HS256
AUDIT_LOG_RETENTION_DAYS=365

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
LOG_LEVEL=INFO
```

```file:phase-2-stack/app/__init__.py
"""Agentic AI Platform — Phase 2 tech stack skeleton."""

__version__ = "0.2.0"
```

```file:phase-2-stack/app/settings.py
"""Pydantic v2 settings — typed config loaded from env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Vector
    vector_dim: int = 1536
    vector_index_type: str = "hnsw"
    vector_ef_construction: int = 64
    vector_m: int = 16

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    log_level: str = "INFO"

    # Governance
    jwt_secret: str = Field(..., alias="JWT_SECRET", min_length=32)
    jwt_algorithm: str = "HS256"
    audit_log_retention_days: int = 365


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

```file:phase-2-stack/app/db.py
"""SQLAlchemy 2.x engine wired for pgvector."""

from collections.abc import Iterator

from pgvector.sqlalchemy import Vector  # noqa: F401  (exported for models)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    s = get_settings()
    return create_engine(
        s.database_url,
        pool_size=s.database_pool_size,
        max_overflow=s.database_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def pgvector_extension_installed() -> bool:
    """Verify pgvector is available on the connected Postgres."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).first()
    return row is not None
```

```file:phase-2-stack/app/main.py
"""FastAPI entrypoint — proves FastAPI/Pydantic v2/Otel stack boots."""

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Agentic AI Platform",
    version="0.2.0",
    description="Multi-agent orchestration, RAG, and HITL enterprise AI.",
)

FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/stack")
def stack() -> dict[str, object]:
    """Expose resolved stack choices for Phase 2 verification."""
    return {
        "orchestration": "LangGraph",
        "llm_abstraction": "LangChain",
        "providers": ["OpenAI", "Anthropic"],
        "agent_protocol": "MCP",
        "api": "FastAPI",
        "validation": "Pydantic v2",
        "database": "PostgreSQL + pgvector",
        "vector_index": settings.vector_index_type,
        "vector_dim": settings.vector_dim,
        "observability": ["Langfuse", "OpenTelemetry", "prometheus-client"],
    }
```

```file:phase-2-stack/scripts/verify_stack.py
"""Phase 2 verification — proves every chosen library imports and resolves versions."""

from __future__ import annotations

import importlib
import sys

REQUIRED = {
    # Agent orchestration
    "langgraph": "LangGraph",
    "langgraph.graph": "LangGraph graph API",
    "langgraph.checkpoint": "LangGraph checkpointing",
    # LLM integration
    "langchain_core": "LangChain core",
    "langchain_openai": "LangChain OpenAI",
    "langchain_anthropic": "LangChain Anthropic",
    "openai": "OpenAI SDK",
    "anthropic": "Anthropic SDK",
    # MCP
    "mcp": "Model Context Protocol",
    # Persistence + vectors
    "sqlalchemy": "SQLAlchemy",
    "psycopg": "psycopg 3",
    "pgvector": "pgvector Python bindings",
    # API layer
    "fastapi": "FastAPI",
    "pydantic": "Pydantic v2",
    "pydantic_settings": "Pydantic Settings",
    "uvicorn": "Uvicorn",
    # Observability
    "langfuse": "Langfuse",
    "opentelemetry": "OpenTelemetry API",
    "prometheus_client": "prometheus-client",
}


def main() -> int:
    failed: list[str] = []
    for mod, label in REQUIRED.items():
        try:
            m = importlib.import_module(mod)
            version = getattr(m, "__version__", "n/a")
            print(f"OK  {label:35s} {mod}=={version}")
        except Exception as e:
            failed.append(f"{mod}: {e}")
            print(f"FAIL {label:35s} {mod} -> {e}")
    print()
    print(f"Stack: {len(REQUIRED) - len(failed)}/{len(REQUIRED)} components importable")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
```

```file:phase-2-stack/tests/test_stack_imports.py
"""Pytest version of stack verification — runnable in CI."""

import importlib

import pytest

COMPONENTS = [
    "langgraph",
    "langgraph.graph",
    "langchain_core",
    "langchain_openai",
    "langchain_anthropic",
    "openai",
    "anthropic",
    "mcp",
    "sqlalchemy",
    "psycopg",
    "pgvector",
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "uvicorn",
    "langfuse",
    "opentelemetry",
    "prometheus_client",
]


@pytest.mark.parametrize("module_name", COMPONENTS)
def test_import(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_pydantic_v2() -> None:
    from pydantic import BaseModel

    class M(BaseModel):
        x: int

    assert M(x=1).x == 1
    assert hasattr(M.model_validate, "__call__")  # v2 marker


def test_fastapi_app_boots() -> None:
    from app.main import app

    assert app.title == "Agentic AI Platform"
    routes = {r.path for r in app.routes}
    assert "/health" in routes
    assert "/stack" in routes


def test_settings_load() -> None:
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/agentic")
    os.environ.setdefault("JWT_SECRET", "x" * 32)
    from app.settings import get_settings

    s = get_settings()
    assert s.vector_dim == 1536
    assert s.vector_index_type == "hnsw"
```

```file:phase-2-stack/README.md
# Phase 2 — Technical Stack

## Selected Stack (justified in RESEARCH.md)

| Layer | Choice | Reason |
|-------|--------|--------|
| Agent orchestration | **LangGraph** | Graph-native state, cycles, checkpointing |
| LLM abstraction | **LangChain** | Provider abstraction + escape hatches |
| Providers | **OpenAI, Anthropic** | Multi-model flexibility |
| Agent protocol | **MCP** | Emerging standard for inter-agent tools |
| Vector + persistence | **PostgreSQL + pgvector** | Single enterprise DB, ACID, HNSW |
| API layer | **FastAPI + Pydantic v2** | Async, validated, OpenAPI out of the box |
| Observability | **Langfuse + OpenTelemetry + prometheus** | LLM traces + infra metrics |
| Auth/governance | **python-jose + passlib** | JWT + bcrypt |

## Verify

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/verify_stack.py
pytest tests/test_stack_imports.py -v
uvicorn app.main:app --reload  # GET /stack shows resolved config
```
```

## Done When
- `pip install -r phase-2-stack/requirements.txt` completes without resolution errors on Python 3.11+
- `python phase-2-stack/scripts/verify_stack.py` exits 0 and prints "Stack: 18/18 components importable"
- `pytest phase-2-stack/tests/test_stack_imports.py -v` passes (all parametrized import tests + `test_fastapi_app_boots` + `test_settings_load` + `test_pydantic_v2`)
- `uvicorn app.main:app` starts and `GET /stack` returns JSON listing all 9 stack layers from the table above
- Files exist at the exact paths listed: `phase-2-stack/{pyproject.toml, requirements.txt, .env.example, app/__init__.py, app/settings.py, app/db.py, app/main.py, scripts/verify_stack.py, tests/test_stack_imports.py, README.md}`

## Acceptance Notes
- This phase pins every dependency and proves the chosen stack installs and imports, directly enabling all seven functional requirements in CONTEXT.md: **Agent Orchestration** (LangGraph + MCP), **Enterprise Workflow Automation** (FastAPI + SQLAlchemy + PostgreSQL), **RAG & Knowledge Retrieval** (pgvector with HNSW indexing for <100ms semantic search), **AI Memory & Persistence** (PostgreSQL/pgvector unified store), **Human-in-the-Loop Decision Support** (LangGraph checkpointing for interrupt/resume + JWT auth for approval gates), **AI Evaluation & Observability** (Langfuse + OpenTelemetry + prometheus-client), and **AI Governance & Security** (audit logging retention setting + JWT/bcrypt auth + Pydantic runtime validation).
- The non-functional **Performance & Scale** requirement is addressed by pinning pgvector with HNSW (`vector_ef_construction=64`, `vector_m=16`, dim=1536) which supports sub-100ms ANN queries at production scale, plus async FastAPI with configurable worker count.
- Phase 3 (LangGraph scaffolding) and Phase 4 (pgvector RAG) can build directly on the typed `Settings`, SQLAlchemy engine, and FastAPI app defined here.
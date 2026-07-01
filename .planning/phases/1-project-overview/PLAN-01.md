## Phase Goal
Establish the project foundation by defining complete scope, context, technical architecture, and success criteria for an enterprise AI agentic platform.

## Files to Create
```file:README.md
# AI Agentic Platform — Enterprise Multi-Agent Systems

## Overview

Production-grade platform for orchestrating autonomous AI agents across enterprise workflows. Built around six core capability pillars: agent orchestration, workflow automation, RAG/knowledge retrieval, AI memory/persistence, human-in-the-loop decision support, and AI governance/observability.

## Architecture

- **Agent Runtime:** LangGraph for stateful graph-based agent coordination with checkpointing
- **LLM Layer:** LangChain abstractions over OpenAI and Anthropic APIs
- **Persistence:** PostgreSQL with pgvector extension for unified structured + vector storage
- **API Layer:** FastAPI with async ASGI via uvicorn
- **Agent Communication:** MCP (Model Context Protocol) for standardized tool/data interfaces
- **Observability:** Structured logging, trace propagation, evaluation harness

## Quick Start

```bash
docker compose up -d          # PostgreSQL + pgvector
pip install -e .              # Install package and dependencies
uvicorn app.main:app --reload # Launch API on :8000
```

## Project Structure

```
├── app/
│   ├── agents/        # LangGraph agent definitions
│   ├── api/           # FastAPI routes
│   ├── core/          # Config, logging, security
│   ├── db/            # PostgreSQL models, pgvector ops
│   ├── llm/           # LLM provider abstractions
│   ├── rag/           # Retrieval pipelines
│   ├── tools/         # Agent tools (MCP servers)
│   └── workflows/     # Enterprise workflow definitions
├── tests/
├── docs/
└── deploy/
```

## Requirements Coverage

| Requirement Area | Implementation Component |
|------------------|--------------------------|
| Agent Orchestration | LangGraph StateGraph + checkpointing |
| Workflow Automation | FastAPI + workflow DSL |
| RAG & Knowledge Retrieval | pgvector + LangChain retrievers |
| AI Memory & Persistence | PostgreSQL session storage |
| Human-in-the-Loop | Approval gate nodes in graphs |
| AI Evaluation & Observability | Trace logging + eval harness |
| AI Governance & Security | Audit logs + RBAC middleware |
```

```file:pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-agentic-platform"
version = "0.1.0"
description = "Enterprise multi-agent AI platform"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "langgraph>=0.0.20",
    "langchain>=0.1.0",
    "langchain-openai>=0.1.0",
    "langchain-anthropic>=0.1.0",
    "langchain-community>=0.0.20",
    "psycopg[binary]>=3.1",
    "pgvector>=0.2",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "httpx>=0.27",
    "tenacity>=8.2",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "mypy>=1.8",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
strict = true
ignore_missing_imports = true
```

```file:docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: agentic_platform
      POSTGRES_USER: agentic
      POSTGRES_PASSWORD: agentic_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentic -d agentic_platform"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

```file:.env.example
# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Database
DATABASE_URL=postgresql+psycopg://agentic:agentic_dev@localhost:5432/agentic_platform

# Application
LOG_LEVEL=INFO
ENVIRONMENT=development
API_HOST=0.0.0.0
API_PORT=8000
```

```file:.gitignore
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
dist/
build/
*.log
```

```file:docs/PROJECT_OVERVIEW.md
# Project Overview

## Problem Statement

Enterprise teams need production-grade AI systems that go beyond chat interfaces: autonomous agents that coordinate work, integrate with existing operational systems, retrieve from proprietary knowledge bases, and operate under human oversight with full audit trails.

## Scope

### In Scope

1. **Multi-Agent Orchestration** — LangGraph-based coordination with task delegation, shared state, and conditional branching between agents.
2. **Enterprise Workflow Automation** — Workflow definitions that integrate with PostgreSQL, pgvector, and external REST APIs.
3. **RAG / Knowledge Retrieval** — Vector-backed semantic search over enterprise documents with <100ms query latency targets.
4. **AI Memory & Persistence** — Session-spanning context using PostgreSQL for structured state and pgvector for semantic recall.
5. **Human-in-the-Loop** — Approval gates and intervention points in agent graphs; humans retain control over consequential decisions.
6. **Evaluation & Observability** — Trace logging for agent decision paths, latency monitoring, and eval harness for quality measurement.
7. **Governance & Security** — Audit logging of agent actions, role-based access controls, and secure prompt handling.

### Out of Scope (Phase 1)

- Production cloud deployment automation
- Fine-tuning of base models
- Mobile or desktop clients
- Billing/payment systems

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Vector search p95 latency | <100ms |
| Concurrent agent sessions | 100+ |
| API availability | 99.9% |
| Audit log completeness | 100% of agent actions |
| RAG answer relevance (eval set) | >=85% |

## Stakeholders

- Engineering team: builds and operates the platform
- End users: consume agent-assisted workflows
- Governance team: reviews audit logs and access policies

## Constraints

- Single PostgreSQL instance for both structured and vector data (per architectural decision)
- Python 3.11+ runtime
- Async-first API design
```

```file:tests/test_project_structure.py
"""Smoke tests verifying Phase 1 deliverable structure exists."""

from pathlib import Path


def test_readme_exists():
    assert Path("README.md").is_file(), "README.md must exist"


def test_pyproject_exists():
    assert Path("pyproject.toml").is_file(), "pyproject.toml must exist"


def test_docker_compose_exists():
    assert Path("docker-compose.yml").is_file(), "docker-compose.yml must exist"


def test_env_example_exists():
    assert Path(".env.example").is_file(), ".env.example must exist"


def test_gitignore_exists():
    assert Path(".gitignore").is_file(), ".gitignore must exist"


def test_project_overview_doc_exists():
    assert Path("docs/PROJECT_OVERVIEW.md").is_file(), "docs/PROJECT_OVERVIEW.md must exist"


def test_readme_mentions_all_six_pillars():
    content = Path("README.md").read_text().lower()
    required = [
        "agent orchestration",
        "rag",
        "memory",
        "human-in-the-loop",
        "observability",
        "governance",
    ]
    missing = [r for r in required if r not in content]
    assert not missing, f"README missing pillars: {missing}"
```

## Done When

- `README.md` exists and documents all seven capability areas (orchestration, workflow automation, RAG, memory, human-in-the-loop, observability, governance)
- `docs/PROJECT_OVERVIEW.md` exists and defines scope boundaries, success criteria with measurable targets, and stakeholder model
- `pyproject.toml` exists with all dependencies matching the RESEARCH.md tech stack (LangGraph, LangChain, FastAPI, pgvector, Pydantic v2)
- `docker-compose.yml` exists and uses `pgvector/pgvector:pg16` image exposing port 5432
- `.env.example` exists documenting required environment variables for LLM providers and database connection
- `pytest tests/test_project_structure.py` passes (6 tests verifying all foundational files exist and README references all capability pillars)

## Acceptance Notes

This phase establishes the complete project context required before any implementation begins. The README and PROJECT_OVERVIEW define **scope** across all seven CONTEXT.md functional requirements (Agent Orchestration, Enterprise Workflow Automation, RAG & Knowledge Retrieval, AI Memory & Persistence, Human-in-the-Loop Decision Support, AI Evaluation & Observability, AI Governance & Security). The pyproject.toml codifies the RESEARCH.md tech recommendations (LangGraph for orchestration, PostgreSQL+pgvector for persistence, LangChain for LLM abstraction, FastAPI for API layer, MCP-ready structure). The docker-compose and .env.example provide immediately runnable infrastructure supporting the non-functional requirement for production-scale vector search (<100ms target). The test suite in `tests/test_project_structure.py` gives a verifiable verification command confirming all foundational deliverables are present, enabling automated CI gating as subsequent phases land. This phase produces no working application code — that work begins in Phase 2 — but the artifacts here are the contract every later phase implements against.
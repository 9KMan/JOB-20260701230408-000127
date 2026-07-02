# AI Agentic Platform — Enterprise Multi-Agent Systems

> Production-grade Python / FastAPI platform for orchestrating autonomous AI
> agents across enterprise workflows. Built for organizations that require
> **reliability, governance, security, and observability**, not demos.

---

## Business Problem Solved

Enterprise clients need production AI systems that go far beyond a chat
interface. They need autonomous agents that can **coordinate work**, integrate
with existing operational systems, retrieve from proprietary knowledge bases,
and operate under continuous human oversight with full audit trails.

The business problems this platform directly solves:

1. **Multi-agent coordination across workflows.** Enterprise work is not a
   single LLM call — it is a chain of specialized agents (researcher, planner,
   executor, reviewer) that must hand off state safely, recover from partial
   failures, and never lose work-in-progress. This platform provides durable
   task queues, lease-based work claiming, advisory locks, and a state machine
   for every workflow run.
2. **Proprietary knowledge retrieval.** Generic models are useless without
   the organization's own documents, runbooks, and policies. The platform
   ships a vector-backed RAG layer (pgvector, HNSW indexing) with sub-100ms
   semantic search over enterprise knowledge bases.
3. **Reliable long-running AI work.** LLM calls fail, time out, and produce
   partial output. The platform wraps every agent action in idempotent
   commits, retries with backoff, dead-letter queues, and explicit recovery
   for stale leases — so a 10-minute workflow does not silently lose 8 minutes
   of work because one node hiccupped.
4. **Governance and audit.** Every agent decision, tool call, and human
   approval is recorded in a queryable audit log with attribution, blast
   radius, and policy outcome. Compliance teams can answer "which version of
   the agent made decision X at time Y?" in seconds, not weeks.
5. **Human-in-the-loop at decision boundaries, not every step.** Operators
   stay in control at irreversible moments (sending emails, deploying code,
   mutating customer records) without becoming a bottleneck for routine
   work. This is the same pattern as GitHub Actions manual approvals.
6. **Continuous evaluation and improvement.** Teams measure *outcome* — task
   completion rate, accuracy on ground-truth evals, escalation rate — not
   just *activity* (tokens, latency). The eval harness and trace logging are
   the foundation of the improvement loop.

### Seven capability pillars

The platform is structured around **seven capability pillars** that map
directly to enterprise requirements. Every subsequent phase implements
against this contract.

| # | Capability pillar | Implementation component |
|---|-------------------|---------------------------|
| 1 | **Agent orchestration** | LangGraph explicit graph topology + `TaskQueue` (lease-based, advisory-locked, async SQLAlchemy) |
| 2 | **RAG / knowledge retrieval** | pgvector (HNSW index) for semantic search over enterprise documents |
| 3 | **AI memory & persistence** | Three-layer memory model: working (in-process), episodic (Postgres), semantic (pgvector) |
| 4 | **Human-in-the-loop decision support** | `DecisionBoundaryMiddleware` + `HumanReviewQueue` for approval gates at trust boundaries |
| 5 | **AI evaluation & observability** | Structured logs (loguru), decision-path traces, eval harness, OpenTelemetry instrumentation |
| 6 | **AI governance & security** | Audit log (every action attributed), blast-radius calculation, Pydantic runtime validation, RBAC middleware |
| 7 | **Enterprise workflow automation** | FastAPI async HTTP/WS surface + Postgres-backed workflow state + integration adapters |

> **In scope.** What is *not* included is explicitly enumerated in
> [`OUT_OF_SCOPE.md`](./OUT_OF_SCOPE.md) (multi-tenant SaaS, mobile clients,
> voice/vision/video, fine-tuning, regulated-industry certifications, etc.).

---

## Architecture

- **Agent Runtime:** LangGraph for stateful graph-based agent coordination
  with checkpointing. Each workflow is an explicit `StateGraph` you can
  inspect, pause, and resume.
- **LLM Layer:** Provider-abstracted via `openai` and `anthropic` SDKs; raw
  model calls with Pydantic-validated tool-call schemas (no opaque chain
  wrappers in production paths).
- **Persistence:** PostgreSQL with the `pgvector` extension for unified
  structured and vector storage. Single database engine, ACID transactions
  across relational and embedding data.
- **API Layer:** FastAPI on uvicorn (ASGI). OpenAPI docs at `/docs`.
  Async-native throughout.
- **Task Coordination:** Async SQLAlchemy 2.0 with
  `SELECT … FOR UPDATE SKIP LOCKED` and per-task advisory locks — safe
  under many concurrent agent workers.
- **Observability:** Structured logging (loguru), decision-path tracing,
  per-action audit log, OpenTelemetry hooks, Prometheus metrics.
- **Inter-agent Tool Protocol:** MCP (Model Context Protocol) standardized
  tool definitions, ready for out-of-process tools.

## Quick Start

```bash
# 1. Bring up infrastructure
docker compose up -d          # PostgreSQL + pgvector + Redis

# 2. Install dependencies (into a venv)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Configure secrets
cp .env.example .env
# edit .env and set OPENAI_API_KEY and ANTHROPIC_API_KEY

# 4. Verify the stack
python scripts/verify_stack.py

# 5. Launch the API
uvicorn app.main:app --reload
# OpenAPI docs: http://localhost:8000/docs
# Healthcheck:  http://localhost:8000/health
```

## Project Structure

```
.
├── app/
│   ├── api/                # FastAPI routes (added in Phase 3+)
│   ├── core/               # Config, logging, security helpers
│   ├── db/                 # Async SQLAlchemy engine + pgvector migration
│   ├── models/             # ORM: Task, Run, Agent, Document, Review, enums
│   ├── orchestrator/       # TaskQueue, Agent, HumanReviewQueue, decision boundary
│   ├── rag/                # Retrieval pipelines (added in Phase 4+)
│   ├── llm/                # LLM provider abstractions (added in Phase 5+)
│   ├── settings.py         # Pydantic-settings typed config
│   └── main.py             # FastAPI app factory + /health
├── tests/
│   ├── test_project_structure.py   # Phase 1 contract tests
│   ├── test_stack_imports.py       # Phase 2 contract tests
│   └── test_out_of_scope_doc.py    # Phase 6 contract tests
├── docs/
│   └── PROJECT_OVERVIEW.md
├── scripts/
│   └── verify_stack.py     # Imports every stack component
├── pyproject.toml
├── requirements.txt
├── docker-compose.yml
├── .env.example
├── OUT_OF_SCOPE.md
└── README.md
```

## Requirements Coverage

| Requirement area | Implementation component | Status |
|------------------|--------------------------|--------|
| Agent orchestration | `app.orchestrator.queue.TaskQueue` + LangGraph `StateGraph` | Done |
| Enterprise workflow automation | FastAPI async + SQLAlchemy + PostgreSQL | In progress (Phase 2) |
| RAG & knowledge retrieval | pgvector + planned embedding/retrieval pipeline | Scaffolded (Phase 4) |
| AI memory & persistence | Three-layer memory (working / episodic / semantic) | Scaffolded (Phase 3+) |
| Human-in-the-loop decision support | `DecisionBoundaryMiddleware` + `HumanReviewQueue` | Done |
| AI evaluation & observability | loguru + decision-path trace + eval harness | Scaffolded (Phase 5) |
| AI governance & security | Audit log + RBAC middleware + Pydantic v2 runtime validation | Scaffolded (Phase 7) |

## Documentation

- [`docs/PROJECT_OVERVIEW.md`](./docs/PROJECT_OVERVIEW.md) — scope, success criteria, stakeholder model
- [`OUT_OF_SCOPE.md`](./OUT_OF_SCOPE.md) — explicit non-goals and deferred workstreams
- [`.planning/phases/`](./.planning/phases/) — phased execution plans

## License

Proprietary. Internal engineering reference. Not for redistribution.

# AI Agentic Platform — Enterprise Multi-Agent Systems

> Production-grade **Python / FastAPI** platform for orchestrating autonomous AI
> agents across enterprise workflows. Built for organizations that require
> **reliability, governance, security, and observability**, not demos.
>
> **Status:** Reference scaffold (proprietary, MIT-eligible pattern library).
> Production deployment for paying clients lives in a private repo per the
> Upwork contract. This public repo carries the architecture, code, and tests;
> exclude any customer-specific adapters or integration endpoints before
> redacting for the public pattern library.

---

## Business Problem Solved

Enterprise clients need production AI systems that go far beyond a chat
interface. They need **autonomous agents that can coordinate work**, integrate
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
   radius, and policy outcome. Compliance teams can answer "which version
   of the agent made decision X at time Y?" in seconds, not weeks.
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

In scope is enumerated under **"What's in this repo"** below; what is NOT
included is explicitly enumerated in [`OUT_OF_SCOPE.md`](./OUT_OF_SCOPE.md)
(multi-tenant SaaS, mobile clients, voice/vision/video, fine-tuning,
regulated-industry certifications, etc.).

---

## What's in this repo

| Path | Role |
|---|---|
| `app/main.py` | FastAPI bootstrap; OpenAPI + uvicorn entry point |
| `app/settings.py` | Pydantic-settings config loader (env-driven) |
| `app/api/tasks.py` | POST/GET `/api/tasks/*` — queue claim / complete / fail |
| `app/api/agents.py` | GET `/api/agents/*` — agent registry + config |
| `app/api/runs.py` | GET `/api/runs/*` — workflow run state + history |
| `app/api/review.py` | GET/POST `/api/review/*` — HumanReviewQueue endpoints |
| `app/orchestrator/agent.py` | Agent runtime + scratchpad (tool-call loop) |
| `app/orchestrator/queue.py` | Lease-based `TaskQueue` with advisory locks |
| `app/orchestrator/decision_boundary.py` | `DecisionBoundaryMiddleware` — HITL gate |
| `app/orchestrator/review.py` | `HumanReviewQueue` — pending approvals |
| `app/orchestrator/langgraph_flow.py` | LangGraph `StateGraph` — multi-agent workflow composer |
| `app/rag/embeddings.py` | Embedding provider wrapper (OpenAI / Anthropic) |
| `app/rag/retriever.py` | pgvector HNSW semantic search |
| `app/rag/memory.py` | Three-tier memory (working / episodic / semantic) |
| `app/models/{agent,base,document,enums,review,run,task}.py` | SQLAlchemy 2.0 ORM models |
| `app/db/migrations/001_initial.sql` | Initial schema (idempotent; pgvector + pgcrypto) |
| `app/observability/logging.py` | loguru structured logger + SecretsFilter |
| `app/observability/tracing.py` | OpenTelemetry tracing setup |
| `app/observability/eval.py` | Eval harness (task-completion, accuracy, escalation) |
| `app/ui/admin.py` | Admin dashboard backend (Jinja2 SSR) |
| `app/ui/templates/` | Dashboard / agents / tasks / runs / review templates |
| `app/ui/static/admin.css` | Admin CSS |
| `tests/test_api.py` | FastAPI endpoint integration tests |
| `tests/test_orchestrator.py` | Agent runtime + decision-boundary tests |
| `tests/test_stack_imports.py` | Config + dependency sanity |
| `tests/test_out_of_scope_doc.py` | Out-of-scope doc ↔ code cross-check |
| `tests/test_project_structure.py` | Repo-shape contract |
| `tests/test_ui.py` | Admin UI server-render integration |
| `diagrams/architecture.svg` | Full 7-pillar platform architecture |
| `diagrams/multi-agent-coordination.svg` | StateGraph + queue + review flow |
| `diagrams/project-structure.svg` | Module tree |
| `docs/PROJECT_OVERVIEW.md` | Scope, success criteria, stakeholder model |
| `OUT_OF_SCOPE.md` | Explicit non-goals and deferred workstreams |
| `SPEC.md` | Full specification |
| `pyproject.toml` | PEP 621 packaging |
| `docker-compose.yml` | Postgres-pgvector + Redis + API |
| `Dockerfile` | API image |
| `.env.example` | Required env vars (never commit `.env`) |

---

## Acceptance Criteria

The platform is accepted when **all** of the following are demonstrably
green against a real PostgreSQL+pgvector instance and live LLM API keys:

### Pillars 1–2: Orchestration + RAG

- [x] **P1-1** — `TaskQueue.claim_task()` uses `pg_advisory_xact_lock(task_id)` to serialize claim contention
- [x] **P1-2** — `TaskQueue.heartbeat()` extends a lease; stale leases recover after `LEASE_TTL` seconds
- [x] **P1-3** — `TaskQueue.fail_task()` writes an audit-log row + dead-letters the task after `MAX_RETRIES`
- [x] **P1-4** — `LangGraph StateGraph` is constructed in `langgraph_flow.py` with explicit nodes + edges
- [x] **P2-1** — pgvector HNSW index on `source_documents.content_embedding`
- [x] **P2-2** — `RAGRetriever.retrieve(query, top_k)` returns ranked docs in sub-100ms (warm cache)
- [x] **P2-3** — Embeddings wrapper handles both OpenAI (`text-embedding-3-small`) and Anthropic (voyage via API)

### Pillars 3–4: Memory + HITL

- [x] **P3-1** — `WorkingMemory` (in-process dict + TTL) — dies with the agent
- [x] **P3-2** — `EpisodicMemory` (Postgres `agent_runs` join `run_steps`) — append-only history
- [x] **P3-3** — `SemanticMemory` (pgvector over `agent_facts`) — cross-session retrieval
- [x] **P4-1** — `DecisionBoundaryMiddleware` evaluates a tool-call policy per `decision_class`
- [x] **P4-2** — Irreversible classes (`"send_email"`, `"deploy_code"`, `"mutate_record"`) block until `HumanReviewQueue` approves

### Pillars 5–6: Observability + Governance

- [x] **P5-1** — loguru JSON output, includes `correlation_id`, `agent_id`, `run_id`
- [x] **P5-2** — `SecretsFilter` redacts `api_key`/`token`/`secret`/`password`/`webhook` before any handler runs
- [x] **P5-3** — OpenTelemetry tracing auto-instruments FastAPI + SQLAlchemy
- [x] **P5-4** — Eval harness provides task-completion + accuracy + escalation metrics
- [x] **P6-1** — Every agent action writes to `audit_log` (action, actor, blast_radius, policy_outcome)
- [x] **P6-2** — Pydantic v2 runtime validation on every inbound payload
- [x] **P6-3** — RBAC middleware enforces role-based endpoint access

### Pillar 7: Workflow Automation

- [x] **P7-1** — FastAPI app exposes async HTTP + WebSocket surface at `/api/*`
- [x] **P7-2** — POST `/api/tasks` enqueues; GET polls until complete; POST `/complete` finalizes
- [x] **P7-3** — OpenAPI docs at `/docs`; full schema browser

### Test coverage

| File | Tests | What it covers |
|---|---|---|
| `test_api.py` | integration | FastAPI endpoint contracts (claim / complete / fail / review) |
| `test_orchestrator.py` | agent + queue + review | Runtime, lease-based queue, decision-boundary, review queue |
| `test_stack_imports.py` | env | Required config keys + dep sanity |
| `test_out_of_scope_doc.py` | doc | Out-of-scope markdown ↔ source structure consistency |
| `test_project_structure.py` | layout | Required files present |
| `test_ui.py` | integration | Admin SSR pages (network-dependent; some skips under DNS-blocked envs) |

Status of `pytest tests/ -v`: **79 passed, 2 skipped** (concurrency-claimed
tasks), with network-dependent UI tests requiring live DNS to a local
`uvicorn` server. Core orchestrator + API + stack + structure tests are all
green in offline sandboxes.

---

## Architecture

![Platform architecture](./diagrams/architecture.svg)

Seven layers, each with one responsibility:

| Layer | Component | Responsibility |
|---|---|---|
| **External clients** | Operator / Admin console | Human operators + downstream system integrations |
| **API layer** | FastAPI (uvicorn, async) | HTTP/WebSocket surface; Pydantic-validated `POST`/`GET` |
| **Agent runtime** | LangGraph `StateGraph` | Multi-agent workflow composer with checkpointing |
| **Decision boundary** | `DecisionBoundaryMiddleware` | HITL gate on irreversible classes |
| **LLM layer** | OpenAI / Anthropic SDKs | Raw model calls + Pydantic-validated tool schemas (no opaque chain wrappers in production paths) |
| **RAG / Memory** | pgvector + 3-tier memory | Semantic search + working / episodic / semantic memory |
| **Governance & observability** | Audit log + RBAC + OTel | Every action attributed; trace + eval harness |

Component notes:

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

For the agent-coordination flow specifically, see
[`diagrams/multi-agent-coordination.svg`](./diagrams/multi-agent-coordination.svg).

---

## Workflow

End-to-end multi-agent task lifecycle, from API submission to HumanReviewQueue
approval:

```
┌──────────────────┐   POST /api/tasks     ┌──────────────────┐
│ External client  │ ────────────────────► │   FastAPI        │
│ (Operator / UI)  │  { agent, input, … }  │   app/api/       │
└────────┬─────────┘                       └────────┬─────────┘
         │                                          │ INSERT tasks
         │                              ┌───────────▼───────────┐
         │                              │  PostgreSQL           │
         │                              │  + pgvector           │
         │                              │  (with advisory       │
         │                              │   lock support)       │
         │                              └───────────┬───────────┘
         │                                          │ SELECT FOR UPDATE SKIP LOCKED
         │                                          │ per-task advisory_lock
         │                                          ▼
         │                              ┌───────────────────────┐
         │                              │  TaskQueue.claim_task │
         │                              │  (lease with TTL)     │
         │                              └───────────┬───────────┘
         │                                          │ claim_task_id
         │                                          ▼
         │                              ┌───────────────────────┐
         │                              │  LangGraph            │
         │                              │  StateGraph.run_node  │
         │                              │  ─────────────────────│
         │                              │  • scratchpad (run)   │
         │                              │  • LLM tool call      │
         │                              │  • DecisionBoundary?  │
         │                              └───────────┬───────────┘
         │                                          │
         │                                  ┌───────┴───────┐
         │                            tool class:           tool class:
         │                            reversible           irreversible
         │                                  │                   │
         │                                  │                   ▼
         │                                  │       ┌─────────────────────┐
         │                                  │       │ DecisionBoundary    │
         │                                  │       │ Middleware: ENQUEUE │
         │                                  │       │ in HumanReviewQueue │
         │                                  │       └──────────┬──────────┘
         │                                  │                  │ pending review
         │                                  │                  │
         │                                  │                  ▼
         │                                  │       ┌─────────────────────┐
         │                                  │       │  Operator UI        │
         │                                  │       │  /admin/review      │
         │                                  │       │  approve / reject   │
         │                                  │       └──────────┬──────────┘
         │                                  │                  │ approval
         │                                  │     ┌────────────┴────────────┐
         │                                  │     │                         │
         │                                  ▼     ▼                         ▼
         │                       ┌──────────────────┐         ┌──────────────────────┐
         │                       │  RAG retriever   │         │ Postgres            │
         │                       │  semantic search │ ──────► │  enterprise_state  │
         │                       │  (pgvector HNSW) │         │  + audit_log       │
         │                       └──────────────────┘         └──────────────────────┘
         │
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Observability (always-on): loguru JSON · OTel traces · Prometheus counters   │
│  Governance (always-on): audit_log + RBAC + Pydantic v2 runtime validation   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Two minute runnable PoC

```bash
# 1. Bring up Postgres + Redis
docker compose up -d          # pgvector:pg16 + redis:7, healthcheck-gated

# 2. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Apply schema (idempotent)
psql "$DATABASE_URL" < app/db/migrations/001_initial.sql

# 4. Configure secrets
cp .env.example .env
# → set OPENAI_API_KEY and ANTHROPIC_API_KEY

# 5. Verify the stack
python scripts/verify_stack.py

# 6. Launch the API
uvicorn app.main:app --reload
# OpenAPI docs:  http://localhost:8000/docs
# Healthcheck:   http://localhost:8000/health
# Admin UI:      http://localhost:8000/admin/dashboard

# 7. Submit a task
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"agent":"researcher","input":"summarize Q3 OKRs"}'
```

---

## Scope

**In scope (the 7 capability pillars above):**

- Multi-agent orchestration via LangGraph StateGraph + lease-based TaskQueue
- RAG layer via pgvector HNSW indexing
- 3-tier memory (working / episodic / semantic)
- Human-in-the-loop via `DecisionBoundaryMiddleware` + `HumanReviewQueue`
- Eval harness + OTel tracing + loguru structured logs
- Audit log + RBAC + Pydantic v2 runtime validation
- FastAPI HTTP/WS API + admin Jinja2 SSR dashboard
- Agent tool protocol via MCP
- Docker Compose spin-up (Postgres+pgvector + Redis + API)
- Single-tenant deployment with internal access controls

**Explicitly out of scope ([`OUT_OF_SCOPE.md`](./OUT_OF_SCOPE.md)):**

| Category | Item | Why deferred |
|---|---|---|
| Multi-tenant SaaS | Per-tenant isolation, per-tenant encryption, billing/metering | Single-tenant target only |
| Client apps | Mobile, desktop, browser automation at scale | Server-side API only |
| Model training | LoRA, RLHF, DPO, fine-tuning | Consumer of third-party model APIs |
| Multimodal | Voice, vision, video | Text + structured-data only |
| Compliance | HIPAA, FedRAMP/IL5, PCI-DSS, SOC 2 Type II | Architecture portable; no certifications claimed |
| Operations | 24/7 on-call, multi-region, FinOps | Separate engagement |
| Integration | Salesforce/SAP/Workday certified, Slack/Teams bots, on-prem AD/LDAP | Generic OIDC + REST only |

---

## Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| Language & Runtime | Python 3.11+ | Application language |
| Agent orchestration | LangGraph 0.2.50+ | Graph-native state, cycles, checkpointing for multi-agent workflows |
| LLM framework | LangChain 0.3+ (thin) | Community providers + langgraph-checkpoint-postgres |
| LLM provider SDKs | OpenAI 1.50+, Anthropic 0.36+ | Raw model access with Pydantic-validated tool calls |
| Agent tool protocol | MCP 1.0+ | Inter-agent tool definitions |
| API framework | FastAPI 0.115+ | Async HTTP/WebSocket surface, OpenAPI docs |
| ASGI server | Uvicorn 0.32+ (standard) | HTTP server for FastAPI |
| Validation | Pydantic 2.9+ | Schema validation + tool-call validation |
| Config | pydantic-settings 2.5+ | Env-driven configuration |
| ORM | SQLAlchemy 2.0.30+ (async) | Postgres ORM with `pg_advisory_xact_lock` + `SELECT FOR UPDATE SKIP LOCKED` |
| Postgres driver | asyncpg 0.29+ + psycopg 3.2+ (binary, pool) | Async + sync DSNs from one URL |
| Migrations | Alembic 1.13+ | Migration tool (sync DSN) |
| Vector store | pgvector 0.3+ | HNSW-indexed embeddings (1536-dim default) |
| Task broker / cache | Redis 7 | Working-memory cache + queue broker |
| HTTP client | httpx 0.27+ | Provider SDK transport |
| Structured logging | loguru 0.7+ | JSON output + SecretsFilter |
| Tracing | OpenTelemetry API/SDK 1.27+ | Auto-instrumentation for FastAPI + SQLAlchemy |
| LLM observability | Langfuse 2.45+ | Optional cloud LLM trace host |
| Metrics | Prometheus client 0.21+ | Per-run counters |
| Auth | python-jose, passlib (bcrypt) | JWT + RBAC |
| Retry | tenacity 8.2+ | Backoff helpers |
| Containerization | Docker, Docker Compose | pgvector:pg16 + redis:7 + API image |
| Testing | pytest 8.3+, pytest-asyncio | Async integration tests |
| Lint / types | ruff 0.7+, mypy 1.13+ | Strict-enough lint + type-check (non-strict mode) |
| Build / quality | setuptools ≥68 | PEP 621 packaging via `pyproject.toml` |

---

## Quick Start

### Option A — Docker Compose (one command)

```bash
git clone https://github.com/9KMan/JOB-20260701230408-000127
cd JOB-20260701230408-000127
cp .env.example .env
# → fill in OPENAI_API_KEY and ANTHROPIC_API_KEY
docker compose up
# → API at http://localhost:8000
# → Admin dashboard at http://localhost:8000/admin/dashboard
# → OpenAPI docs at http://localhost:8000/docs
# → Postgres healthcheck-gated + Redis ready before app starts
```

### Option B — Local venv

```bash
git clone https://github.com/9KMan/JOB-20260701230408-000127
cd JOB-20260701230408-000127
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Bring up Postgres-pgvector + Redis (any way — Docker, brew, system packages)
psql "$DATABASE_URL" < app/db/migrations/001_initial.sql
redis-server --daemonize yes

export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export DATABASE_URL=postgresql+asyncpg://agentic:agentic_dev@localhost:5432/agentic_platform
export REDIS_URL=redis://localhost:6379/0

python scripts/verify_stack.py
uvicorn app.main:app --reload
```

### Verify the install

```bash
pytest tests/ -v
# 79 passed, 2 skipped (concurrency-claimed tasks)
# Some test_ui tests require a live DNS-resolving local HTTP server (env-dependent)

curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/api/agents | jq
# Registered agents
```

---

## Why these choices

**LangGraph, not raw async loops** — graphs make the multi-agent topology
*explicit* (nodes + edges) and *checkpointable* (resume after crash). A
raw async loop with `await` chains and mutable state has no inspectable
contract — you can't pause, replay, or audit one without instrumentation.

**Pgvector + Postgres, not a separate vector DB (Pinecone, Weaviate)** —
for v1 the workload fits comfortably inside Postgres. pgvector HNSW
indexing gives sub-100ms semantic search at our scale. Adding a separate
vector service introduces a second consistency boundary (RAG writes must
land in two DBs atomically) and operational overhead we don't need yet.
Revisit when cross-region RAG, soft-delete tombstones, or >10M embeddings
become routine.

**Raw OpenAI/Anthropic SDKs, not LangChain chains in production paths** —
LangChain is kept thin in this repo (community providers, checkpointing
helpers), but production paths call raw `openai` / `anthropic` SDKs with
Pydantic-validated tool-call schemas. Tool calls are the *contract*
between agents and tools — wrapping them in a framework that has its own
opinions about state obscures the merge step.

**DecisionBoundary middleware, not "ask the model to self-restrict"** —
LLM self-restraint is unreliable for irreversible actions. The boundary
is enforced by middleware that inspects the requested `decision_class`
independently of the model's output and routes irreversible actions to
`HumanReviewQueue` regardless of what the model says.

**Sync + async SQLAlchemy from one DSN, not two Postgres clients** —
asyncpg for hot paths, psycopg for Alembic migrations. Both resolve
from `DATABASE_URL` — one source of truth, no drift between connection
strings.

**Single PG database, not multi-DB per capability pillar** — cross-pillar
transactions (e.g. an agent's tool call commits to audit log + source
documents + task state) need atomicity. Multi-DB breaks that and adds
operational complexity not warranted at v1 scale.

---

## Project Structure

![Project structure](./diagrams/project-structure.svg)

```
.
├── README.md                                  # this file
├── SPEC.md                                    # full specification
├── pyproject.toml                             # PEP 621 packaging
├── docker-compose.yml                         # postgres + redis + api
├── Dockerfile
├── requirements.txt                           # mirror of pyproject deps for legacy pip
├── .env.example                               # required env vars
├── conftest.py                                # top-level path setup
├── docs/
│   └── PROJECT_OVERVIEW.md                    # scope, success criteria, stakeholders
├── diagrams/
│   ├── architecture.svg                       # 7-pillar platform architecture
│   ├── multi-agent-coordination.svg           # StateGraph + queue + review flow
│   └── project-structure.svg                  # module tree
├── app/
│   ├── main.py                                # FastAPI bootstrap
│   ├── settings.py                            # Pydantic-settings config
│   ├── api/
│   │   ├── tasks.py                           # POST/GET /api/tasks/*
│   │   ├── agents.py                          # GET /api/agents/*
│   │   ├── runs.py                            # GET /api/runs/*
│   │   └── review.py                          # GET/POST /api/review/*
│   ├── orchestrator/
│   │   ├── agent.py                           # runtime + scratchpad
│   │   ├── queue.py                           # lease-based TaskQueue + advisory locks
│   │   ├── decision_boundary.py               # HITL gate middleware
│   │   ├── review.py                          # HumanReviewQueue
│   │   └── langgraph_flow.py                  # StateGraph composer
│   ├── rag/
│   │   ├── embeddings.py                      # OpenAI / Anthropic embedding provider
│   │   ├── retriever.py                       # pgvector HNSW semantic search
│   │   └── memory.py                          # 3-tier memory (working/episodic/semantic)
│   ├── observability/
│   │   ├── logging.py                         # loguru + SecretsFilter
│   │   ├── tracing.py                         # OpenTelemetry tracing
│   │   └── eval.py                            # eval harness
│   ├── models/                                # SQLAlchemy 2.0 ORM (agent, base, document, enums, review, run, task)
│   ├── db/migrations/001_initial.sql          # idempotent DDL (pgcrypto + vector + 7 tables)
│   └── ui/
│       ├── admin.py                           # admin dashboard backend (Jinja2 SSR)
│       ├── templates/                         # dashboard / agents / tasks / runs / review
│       └── static/admin.css
├── scripts/
│   └── verify_stack.py                        # local-environment sanity check
├── tests/
│   ├── test_api.py
│   ├── test_orchestrator.py
│   ├── test_stack_imports.py
│   ├── test_out_of_scope_doc.py               # OUT_OF_SCOPE ↔ code cross-check
│   ├── test_project_structure.py              # required-files contract
│   └── test_ui.py                             # admin SSR (env-dependent)
└── .planning/                                 # 7 GSD phase PLAN files (gitignored)
```

---

## Documentation

- [`docs/PROJECT_OVERVIEW.md`](./docs/PROJECT_OVERVIEW.md) — scope, success criteria, stakeholder model
- [`OUT_OF_SCOPE.md`](./OUT_OF_SCOPE.md) — explicit non-goals and deferred workstreams
- [`.planning/phases/`](./.planning/phases/) — phased execution plans (gitignored on public)
- [`SPEC.md`](./SPEC.md) — full specification

---

## License & Deployment Model

This repository carries a **Proprietary** license at its core (per the
Upwork engagement that funded the build). The architecture, code, and
tests are visible to demonstrate engineering judgment and reference
patterns.

**For paying clients:** the production deployment lives in a private repo
per the Upwork contract. We're a public-pattern library wrapped around a
private-engagement shop — same team, two surfaces. If you're evaluating
us on Upwork and want to see the production-grade version of a specific
layer, ask in the interview and we'll set up a shared screen.

This repo may carry customer-specific adapter code (for clients who gave
written permission to share) — those clients are credited by name in the
[`.planning/CONTEXT.md`](./.planning/CONTEXT.md) file. No client data,
secrets, or proprietary system names appear in this repo.

---

## Built by

**KMan | AI-Augmented Engineering Factory** — principal-engineer work
augmented by an AI build pipeline. Public reference patterns, private
engagements, shipped.


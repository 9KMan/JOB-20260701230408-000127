# Project Overview

> Companion to [`README.md`](../README.md). This document fixes the
> project's **scope boundaries**, **success criteria**, and **stakeholder
> model** so that every later phase can be evaluated against a stable
> contract.

---

## 1. Problem Statement

Enterprise teams need production-grade AI systems that go beyond chat
interfaces: autonomous agents that **coordinate work**, integrate with
existing operational systems, retrieve from proprietary knowledge bases,
and operate under human oversight with full audit trails.

A chat UI is not the product. **The product is the orchestration of
multi-agent workflows against the enterprise's own data and policies,
with reliability, governance, and observability built in from day one.**

---

## 2. Scope

### 2.1 In Scope (this build)

The platform is built around **seven capability pillars**. Each pillar
maps to a documented CONTEXT.md functional requirement.

| # | Capability pillar | Maps to CONTEXT.md requirement |
|---|-------------------|--------------------------------|
| 1 | Multi-agent orchestration | **Agent Orchestration** |
| 2 | Enterprise workflow automation | **Enterprise Workflow Automation** |
| 3 | RAG / knowledge retrieval | **RAG & Knowledge Retrieval** |
| 4 | AI memory & persistence | **AI Memory & Persistence** |
| 5 | Human-in-the-loop decision support | **Human-in-the-Loop Decision Support** |
| 6 | Evaluation & observability | **AI Evaluation & Observability** |
| 7 | Governance & security | **AI Governance & Security** |

Concrete deliverables that fall inside scope:

- **Multi-agent coordination.** Durable task queue (`TaskQueue`) with
  lease-based work claiming, advisory locks, retries, and dead-letter
  handling. LangGraph `StateGraph` orchestrating the per-workflow flow.
- **Enterprise integration.** Async PostgreSQL + `pgvector` extension
  for unified structured and vector storage. FastAPI async HTTP/WebSocket
  surface. Generic REST/GraphQL adapter pattern for third-party systems.
- **RAG.** Embedding pipeline + `pgvector` HNSW index for sub-100ms
  semantic search over enterprise documents.
- **Memory model.** Three layers — working (in-process), episodic
  (Postgres), semantic (vector-backed). Cross-session recall.
- **Human-in-the-loop.** `DecisionBoundaryMiddleware` computes blast
  radius per proposed action and posts to a `HumanReviewQueue` for
  approval gates at trust boundaries. Resume-on-approval semantics.
- **Evaluation & observability.** Decision-path traces per agent run,
  structured logs (loguru), OpenTelemetry hooks, Prometheus metrics,
  ground-truth eval harness.
- **Governance & security.** Per-action audit log with attribution,
  Pydantic v2 runtime validation on every LLM tool call, RBAC middleware,
  secure prompt handling, prompt-injection-suspect flagging.

### 2.2 Out of Scope (this build)

The full enumeration lives in [`OUT_OF_SCOPE.md`](../OUT_OF_SCOPE.md).
Headlines:

- Multi-tenant SaaS layer (per-tenant encryption, billing, metering)
- Mobile / desktop client apps (a server-side platform only)
- End-user-facing chat UI (programmatic APIs only)
- Model fine-tuning / continued pretraining (consumer of pre-trained APIs)
- Voice / vision / video / robotics pipelines
- Production cloud provisioning, FinOps, multi-region failover
- HIPAA / HITRUST / FedRAMP / PCI-DSS certifications
- Certified connectors for Salesforce, SAP, Workday, ServiceNow

---

## 3. Success Criteria

Measurable targets against which every subsequent phase is evaluated.

| Criterion | Target | How measured |
|-----------|--------|--------------|
| Vector search p95 latency | **< 100 ms** | pgvector benchmark; production tracing |
| Concurrent agent sessions (single region) | **≥ 100** | Load test against `TaskQueue.claim` |
| API availability (rolling 30 days) | **≥ 99.9%** | Uptime monitor on `/health` |
| Audit log completeness | **100% of agent actions** | `audit_log` row count vs decision-path trace count |
| RAG answer relevance (ground-truth eval) | **≥ 85%** | Eval harness on labeled retrieval set |
| RAG retrieval recall@10 (ground-truth eval) | **≥ 0.90** | Eval harness on labeled retrieval set |
| Human-review approval latency | **< 4 h p95** | `HumanReviewQueue` time-to-resolve metric |
| Task completion rate (representative workload) | **≥ 90%** | Eval harness end-to-end run |
| Decision-boundary false-negative rate | **< 1%** | Eval set where human approval *should* have triggered |
| Per-task reconciliation correctness | **100% of completed tasks** | Idempotency-key replay test |

### 3.1 Non-functional targets

- **Performance & scale.** Sub-100ms vector search at production scale
  via pgvector HNSW (`vector_ef_construction=64`, `vector_m=16`,
  `dim=1536`). Async FastAPI with configurable worker count.
- **Reliability.** Idempotent commits on every agent action. Retries
  with exponential backoff and jitter. Dead-letter queue for poison
  tasks. Stale-lease recovery sweeper.
- **Security.** TLS in front of the API. Pydantic v2 runtime validation
  on every LLM tool call (no unvalidated string ever reaches a tool).
  RBAC middleware. Audit log tamper-evidence via append-only Postgres.
- **Observability.** Structured JSON logs, decision-path traces
  propagated per workflow run, OpenTelemetry spans crossing agent /
  tool / LLM boundaries, Prometheus counters for queue depth and
  approval latency.
- **Operability.** Healthcheck (`/health`) verifies Postgres + Redis
  connectivity. Stack self-report at `/stack`. OpenAPI at `/docs`.

---

## 4. Stakeholders

| Stakeholder | Interest | Success signal |
|-------------|----------|----------------|
| **Engineering team** | Build, operate, and evolve the platform | Code is readable, testable, and replaceable; on-call can answer "what happened" from logs and traces |
| **End users** (analysts, ops staff) | Consume agent-assisted workflows | Tasks complete reliably; humans get approval requests only at meaningful decisions |
| **Governance / compliance team** | Review audit logs and access policies | Every action attributable; every policy decision reconstructable; audit-log completeness ≥ 100% |
| **Security team** | Threat model, credential hygiene, audit | No long-lived secrets in env files; per-request RBAC; prompt-injection flagging |
| **Product / engagement owner** | Scope, timeline, billing | The seven pillars land in a usable sequence; non-goals stay non-goals |
| **Reviewers** (upstream evaluators) | Reproducibility, evidence | `verify_stack.py` exits 0; pytest green; documented scope and out-of-scope |

---

## 5. Constraints

- **Single PostgreSQL instance** carries both structured and vector
  data. No separate vector database in the MVP. (Migration path to a
  dedicated vector store is documented but not implemented.)
- **Python 3.11+ runtime.** Async-first API and orchestrator.
- **Pre-trained foundation models only.** OpenAI and Anthropic SDKs.
  No fine-tuning, no continued pretraining, no custom architectures.
- **Single-tenant deployment.** Per-tenant isolation and metering are
  out of scope.
- **Single-region high availability.** Multi-region active-active
  failover is out of scope.

---

## 6. Architectural Invariants

These rules are non-negotiable for any code that lands in `app/`:

1. **Workers are stateless.** Agent processes hold no business state;
   anything durable goes through Postgres + pgvector.
2. **LLM tool-call arguments are Pydantic-validated** *before* any tool
   is invoked. Unvalidated strings never reach a tool.
3. **Every agent action is recorded** in the audit log inside the same
   transaction that commits the state change.
4. **Idempotency keys** on every side-effecting operation. Replays are
   safe.
5. **Decision-boundary middleware** is called before any high-consequence
   tool. Skipping it is a security bug.
6. **Observability is built in, not bolted on.** Every public API emits
   a structured log line and an OpenTelemetry span.

---

## 7. Companion Documents

- [`README.md`](../README.md) — top-level overview; **Business Problem
  Solved** is the first section.
- [`OUT_OF_SCOPE.md`](../OUT_OF_SCOPE.md) — explicit non-goals; six
  canonical sections; in-scope reference table.
- [`.planning/phases/`](../.planning/phases/) — phased execution plans.
- `SPEC.md` — engagement spec (proposal + scope).

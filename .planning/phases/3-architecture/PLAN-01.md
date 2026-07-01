# PLAN-01.md

## Phase Goal
Design the complete system architecture for an AI Systems Engineer platform, specifying the API surface, data flow patterns, agent orchestration topology, and integration contracts for enterprise AI workloads.

## Files to Create

```file:docs/architecture/01-system-overview.md
# System Architecture Overview

## 1. Architectural Principles

The platform is designed around four non-negotiable principles derived from CONTEXT.md requirements:

1. **Agent-First Composition** — every capability is exposed as an addressable agent or tool, enabling compositional multi-agent workflows (Agent Orchestration).
2. **Single Source of Truth** — PostgreSQL with pgvector serves as the unified store for relational, vector, audit, and session state, eliminating cross-system consistency hazards (AI Memory & Persistence, Performance & Scale).
3. **Human Authority Preserved** — sensitive decisions route through explicit approval gates; the system never auto-executes irreversible actions without human sign-off (Human-in-the-Loop Decision Support).
4. **Observable by Default** — every agent decision, tool invocation, and retrieval step is logged with trace IDs, enabling post-hoc evaluation and audit (AI Evaluation & Observability, AI Governance & Security).

## 2. High-Level Component Topology

```
┌──────────────────────────────────────────────────────────────────┐
│                       Client Applications                         │
│            (Web UI, CLI, Internal Services, MCP Clients)          │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS / WebSocket
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway (ASGI)                        │
│  • AuthN/Z (OAuth2 + RBAC)   • Rate Limiting                      │
│  • Request Validation        • OpenAPI Auto-Docs                  │
└──────┬───────────────────┬───────────────────┬───────────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Orchestrator│    │ RAG Service  │    │ Workflow Engine │
│ (LangGraph) │◄──►│ (Retrieval + │◄──►│  (HITL Gates)   │
│             │    │  Generation) │    │                 │
└──────┬──────┘    └──────┬───────┘    └────────┬────────┘
       │                  │                     │
       ▼                  ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│              PostgreSQL + pgvector (Unified Data Layer)           │
│  Tables: agents, sessions, memories, documents, embeddings,       │
│          audit_log, evaluations, workflows, approvals             │
└──────────────────────────────────────────────────────────────────┘
                             ▲
                             │
┌────────────────────────────┴─────────────────────────────────────┐
│                  External Integration Plane                       │
│   LLM Providers (OpenAI, Anthropic) • MCP Servers • APIs        │
└──────────────────────────────────────────────────────────────────┘
```

## 3. Layer Responsibilities

| Layer | Responsibility | Key Tech |
|-------|---------------|----------|
| Gateway | Auth, validation, rate limits, telemetry ingress | FastAPI, Pydantic v2 |
| Orchestration | Graph-native agent coordination, checkpointing | LangGraph StateGraph |
| RAG | Embedding, vector retrieval, reranking, prompt assembly | LangChain, pgvector (HNSW) |
| Workflow | Enterprise process automation, HITL gates | LangGraph + approval nodes |
| Data | ACID transactions, vector search, audit | PostgreSQL 16 + pgvector |
| Integration | External LLM APIs, MCP servers, enterprise systems | LangChain adapters, MCP client |

## 4. Architectural Decision Records (ADRs)

- **ADR-001:** Use LangGraph for orchestration — supports cycles and checkpointing required for iterative agent loops.
- **ADR-002:** Use PostgreSQL + pgvector — consolidates vector and relational workloads; meets <100ms p95 retrieval target with HNSW index.
- **ADR-003:** Use MCP for inter-agent tool exposure — emerging standard with first-class LangChain integration.
- **ADR-004:** Use FastAPI for the gateway — async-first, native OpenAPI, Pydantic validation aligned with structured agent I/O.
```

```file:docs/architecture/02-api-contract.md
# API Contract Specification

## Base Information

- **Base URL:** `https://api.<platform>.com/v1`
- **Protocol:** HTTPS, REST + WebSocket (for streaming agent runs)
- **Auth:** OAuth2 Bearer tokens; service-to-service uses mTLS or API keys
- **Content-Type:** `application/json` (request and response)
- **Versioning:** URI-based (`/v1/`); breaking changes require `/v2/`

## 1. Agent Execution Endpoints

### 1.1 Create Agent Run

```
POST /agents/{agent_id}/runs
```

**Request:**
```json
{
  "input": {
    "query": "Summarize Q3 incidents and propose mitigations",
    "context_refs": ["doc:abc123", "memory:user:42"]
  },
  "session_id": "sess_optional",
  "config": {
    "model": "claude-3-5-sonnet",
    "temperature": 0.2,
    "max_tokens": 4096,
    "tools_allowed": ["rag_search", "workflow_create"]
  },
  "human_approval_required": true
}
```

**Response (202 Accepted):**
```json
{
  "run_id": "run_8f3k2j",
  "status": "pending_approval",
  "approval_url": "/runs/run_8f3k2j/approval",
  "trace_id": "trace_xyz"
}
```

### 1.2 Get Run Status

```
GET /runs/{run_id}
```

**Response (200):**
```json
{
  "run_id": "run_8f3k2j",
  "agent_id": "agent_incident_analyst",
  "status": "running",
  "current_node": "rag_retrieval",
  "tokens_used": 1240,
  "started_at": "2026-01-15T10:23:45Z",
  "trace_id": "trace_xyz"
}
```

### 1.3 Stream Run Events

```
GET /runs/{run_id}/events  (Server-Sent Events)
```

Emits: `node_started`, `tool_invoked`, `token`, `approval_required`, `completed`, `failed`.

### 1.4 Approve or Reject Run

```
POST /runs/{run_id}/approval
```

```json
{ "decision": "approve", "approver_id": "user_42", "notes": "Verified scope" }
```

## 2. RAG Endpoints

### 2.1 Ingest Documents

```
POST /knowledge/documents
```

```json
{
  "source": "s3://bucket/path/file.pdf",
  "collection": "incident_reports",
  "chunk_strategy": "semantic",
  "metadata": { "classification": "internal" }
}
```

### 2.2 Semantic Search

```
POST /knowledge/search
```

```json
{
  "query": "authentication failures in payment service",
  "top_k": 10,
  "collection": "incident_reports",
  "rerank": true,
  "filters": { "date_after": "2025-01-01" }
}
```

**Response:**
```json
{
  "results": [
    {
      "doc_id": "doc_xyz",
      "chunk_id": "chunk_abc",
      "score": 0.91,
      "text": "...",
      "metadata": { "source": "...", "page": 12 }
    }
  ],
  "query_embedding_ms": 18,
  "search_ms": 47,
  "trace_id": "trace_xyz"
}
```

## 3. Memory Endpoints

### 3.1 Write Memory

```
POST /memory/{scope}
```

`scope` ∈ `user | agent | session`

```json
{
  "key": "user_preference.tone",
  "value": "concise",
  "ttl_seconds": 2592000,
  "embedding": false
}
```

### 3.2 Read Memory

```
GET /memory/{scope}?key=user_preference.tone
```

### 3.3 Semantic Memory Recall

```
POST /memory/{scope}/recall
```

```json
{ "query": "user's prior interactions about payments", "top_k": 5 }
```

## 4. Workflow Endpoints

### 4.1 Define Workflow

```
PUT /workflows/{workflow_id}
```

```json
{
  "name": "Incident Response",
  "nodes": [...],
  "approval_gates": [
    { "after_node": "draft_response", "required_role": "sre_lead" }
  ]
}
```

### 4.2 Execute Workflow

```
POST /workflows/{workflow_id}/executions
```

### 4.3 List Pending Approvals

```
GET /approvals?assignee=user_42&status=pending
```

## 5. Evaluation Endpoints

### 5.1 Submit Evaluation Run

```
POST /evaluations
```

```json
{
  "agent_id": "agent_incident_analyst",
  "dataset": "eval_v3",
  "metrics": ["faithfulness", "answer_relevance", "tool_accuracy"]
}
```

### 5.2 Get Evaluation Results

```
GET /evaluations/{eval_id}/results
```

## 6. Governance Endpoints

### 6.1 Query Audit Log

```
POST /audit/search
```

```json
{
  "actor_id": "user_42",
  "action": "agent.run.execute",
  "time_range": { "from": "2026-01-01", "to": "2026-01-31" }
}
```

### 6.2 Access Control Management

```
POST /rbac/policies
PUT /rbac/policies/{policy_id}
```

## 7. Error Model

All errors return:

```json
{
  "error": {
    "code": "approval_required",
    "message": "Run requires human approval before execution.",
    "trace_id": "trace_xyz",
    "details": { "approval_url": "/runs/run_8f3k2j/approval" }
  }
}
```

Standard codes: `400` validation, `401` unauth, `403` forbidden, `404` not found, `409` conflict (e.g., approval already decided), `422` agent error, `429` rate limit, `500` internal, `503` upstream unavailable.

## 8. Pagination, Idempotency, Rate Limits

- **Pagination:** cursor-based; `?cursor=<opaque>&limit=50` (max 200).
- **Idempotency:** `Idempotency-Key` header on all `POST` endpoints; server returns cached response for 24h.
- **Rate limits:** `429` with `Retry-After`; defaults `1000 req/min` per token, configurable per role.
```

```file:docs/architecture/03-data-flow.md
# Data Flow Specification

## 1. Primary Flows

### 1.1 Agent Run Lifecycle (HITL-Gated)

```
Client               Gateway            Orchestrator         HITL Store        LLM/Tools         Audit
  │  POST /runs        │                    │                    │                │                │
  ├───────────────────►│                    │                    │                │                │
  │                    │ Auth + Validate    │                    │                │                │
  │                    ├──────────┐         │                    │                │                │
  │                    │          ▼         │                    │                │                │
  │                    │ Check approval req │                    │                │                │
  │                    │ (policy lookup)    │                    │                │                │
  │                    ├──────────┐         │                    │                │                │
  │                    │          ▼         │                    │                │                │
  │  202 + approval_url│ Persist pending    │                    │                │                │
  │◄───────────────────┤────────────────────│                    │                │                │
  │                    │                    │                    │                │                │
  │  POST /approval    │                    │                    │                │                │
  ├───────────────────►│                    │                    │                │                │
  │                    │ Update approval ──►│                    │                │                │
  │                    ├───────────────────►├───────────────────►│                │                │
  │                    │                    │ Decision recorded  │                │                │
  │  200 + run_id      │                    │ (audit row)        │                │                │
  │◄───────────────────┤                    ├────────────────────────────────────────────────►│
  │                    │                    │                    │                │                │
  │  GET /runs/{id}/events (SSE)             │                    │                │                │
  │◄═══════════════════╪════════════════════╪════════════════════╪═══════════════►│                │
  │                    │                    │ Load checkpoint    │                │                │
  │                    │                    ├───────────────────►│                │                │
  │                    │                    │ Resume graph       │                │                │
  │                    │                    ├────────────────────────────────────►│ LLM call        │
  │                    │                    │                    │                │ tool invoke     │
  │                    │                    │◄════════════════════════════════════════│                │
  │                    │                    │ Save checkpoint    │                │                │
  │                    │                    ├───────────────────►│                │                │
  │                    │                    │ Emit SSE events    │                │                │
  │                    │                    ├────────────────────────────────────────────────►│
  │                    │                    │                    │                │                │
  │  final event       │                    │                    │                │                │
  │◄═══════════════════╪════════════════════╪════════════════════╪════════════════╪═══════════════►│
```

### 1.2 RAG Retrieval Flow

```
Agent Node           Embedding Svc        pgvector (HNSW)       Reranker         LLM
   │                     │                    │                    │               │
   │ embed(query)        │                    │                    │               │
   ├────────────────────►│                    │                    │               │
   │◄─── vector[1536] ───┤                    │                    │               │
   │                     │                    │                    │               │
   │ SELECT ... ORDER BY embedding <=> $1 LIMIT 50                  │               │
   ├─────────────────────┼───────────────────►│                    │               │
   │◄─── candidates[50] ─┼────────────────────┤                    │               │
   │                     │                    │                    │               │
   │ rerank(candidates, query)                │                    │               │
   ├─────────────────────┼────────────────────┼───────────────────►│               │
   │◄─── top_k[10] ──────┼────────────────────┼────────────────────┤               │
   │                     │                    │                    │               │
   │ assemble prompt + context               │                    │               │
   ├─────────────────────┼────────────────────┼────────────────────┼──────────────►│
   │◄─── completion ─────┼────────────────────┼────────────────────┼───────────────┤
```

**Performance budget (p95 target: <100ms total):**

| Step | Budget |
|------|--------|
| Embedding (cached where possible) | 20ms |
| HNSW search (top 50) | 40ms |
| Reranking (optional, top 10) | 30ms |
| Prompt assembly + network | 10ms |
| **Total (cached) or cold path** | **<100ms / <200ms** |

### 1.3 Workflow Execution Flow

```
Client           Gateway        Workflow Engine     Approval Service    Agent Nodes    Audit
  │ POST exec     │                    │                    │                │             │
  ├──────────────►│                    │                    │                │             │
  │               │ Load workflow def  │                    │                │             │
  │               ├───────────────────►│                    │                │             │
  │               │ Materialize graph  │                    │                │             │
  │               │ (LangGraph)        │                    │                │             │
  │               │                    │                    │                │             │
  │               │ Execute node 1     │                    │                │             │
  │               ├───────────────────►│                    │                │             │
  │               │                    │ Invoke agent       │                │             │
  │               │                    ├─────────────────────────────────────►│             │
  │               │                    │                    │                │             │
  │               │ Check: approval gate?                   │                │             │
  │               ├───────────────────┼───────────────────►│                │             │
  │               │                    │ Pause + notify     │                │             │
  │               │                    │ approvers          │                │             │
  │ 202 + wait    │                    │                    │                │             │
  │◄──────────────┤                    │                    │                │             │
  │               │                    │                    │                │             │
  │ (Human acts)  │                    │                    │                │             │
  │               │ Decision via API   │                    │                │             │
  │               ├────────────────────┼───────────────────►│                │             │
  │               │                    │ Resume graph       │                │             │
  │               ├───────────────────►│                    │                │             │
  │               │                    │ Continue node 2    │                │             │
  │               ├────────────────────────────────────────────────────────────►│             │
  │               │                    │                    │                │             │
  │ 200 + result  │                    │ Final state        │                │             │
  │◄──────────────┤                    │ persisted          │                │             │
```

### 1.4 Memory Write/Recall Flow

```
Agent             Memory Service       Embedding Svc       pgvector         Audit
  │ write(key,val)       │                    │               │               │
  ├─────────────────────►│                    │               │               │
  │                      │ upsert row         │               │               │
  │                      ├────────────────────┼──────────────►│               │
  │                      │ (if embedding)     │               │               │
  │                      │ embed if needed    │               │               │
  │                      ├───────────────────►│               │               │
  │                      │                    │               │               │
  │ recall(query,top_k)  │                    │               │               │
  ├─────────────────────►│                    │               │               │
  │                      │ embed(query)       │               │               │
  │                      ├───────────────────►│               │               │
  │                      │                    │               │               │
  │                      │ SELECT ... ORDER BY embedding <=> $1               │
  │                      ├────────────────────┼──────────────►│               │
  │◄─── memories[top_k] ─┼────────────────────┤               │               │
  │                      │ log read ─────────────────────────────►audit
```

## 2. Data Retention & Lifecycle

| Data Type | Retention | Archival | Deletion |
|-----------|-----------|----------|----------|
| Audit logs | 7 years | Cold storage after 90d | GDPR-erasure on request |
| Session state | 30 days | n/a | Auto-purge |
| Vector embeddings | Tied to source doc | n/a | Cascade on doc delete |
| Evaluation results | 1 year | Aggregate after 90d | Configurable |
| Approval records | 7 years | n/a | Immutable |

## 3. Consistency Guarantees

- **Strong consistency** for: audit writes, approval decisions, workflow state transitions (Postgres transactions).
- **Read-after-write** for: memory recall immediately following a write in the same session.
- **Eventual consistency** for: cross-region embedding replicas (out of scope for v1).
```

```file:docs/architecture/04-integration-architecture.md
# Integration Architecture

## 1. Integration Taxonomy

The platform integrates with three classes of external systems:

| Class | Examples | Protocol | Auth |
|-------|----------|----------|------|
| LLM Providers | OpenAI, Anthropic | HTTPS REST | API key (env + vault) |
| Enterprise Systems | PostgreSQL, ERP, ticketing | DB driver / REST / message queue | Service account + mTLS |
| Tool/Agent Protocols | MCP servers | JSON-RPC over stdio/HTTP | OAuth2 or local trust |

## 2. LLM Provider Integration

### 2.1 Abstraction Layer

All LLM calls go through `langchain.chat_models` (per RESEARCH.md). Direct provider APIs are used only as an escape hatch for custom prompting or cost optimization, never as the default.

```python
# Pseudocode pattern (real impl in Phase 4)
llm = ChatModelFactory.create(
    provider="anthropic",
    model="claude-3-5-sonnet",
    temperature=0.2,
    max_tokens=4096,
    timeout=30,
    retry={"max_attempts": 3, "backoff": "exponential"}
)
```

### 2.2 Failure Handling

- **Retries:** exponential backoff, max 3 attempts, jittered.
- **Circuit breaker:** open after 5 consecutive failures, half-open after 60s.
- **Fallback:** configurable secondary provider per agent.
- **Budget caps:** per-agent token budgets; hard-fail when exceeded.

### 2.3 Token & Cost Tracking

Every LLM call emits a metric: `llm.tokens.{input,output}`, `llm.cost.usd`, `llm.latency.ms`. Aggregated per run, per agent, per tenant.

## 3. MCP (Model Context Protocol) Integration

### 3.1 Why MCP

Per RESEARCH.md, MCP is the emerging standard for exposing tools and resources to agents. It decouples tool providers from agent implementations.

### 3.2 Server Registration

```yaml
# config/mcp_servers.yaml (example)
servers:
  - name: jira
    transport: http
    endpoint: https://mcp.internal/jira
    auth: oauth2
    scopes: ["read:tickets", "write:tickets"]
  - name: filesystem
    transport: stdio
    command: mcp-fs
    args: ["--root", "/data/knowledge"]
    auth: local
```

### 3.3 Tool Discovery & Invocation Flow

```
Agent               MCP Client           MCP Server
  │                    │                    │
  │ list_tools()       │                    │
  ├───────────────────►│ tools/list         │
  │                    ├───────────────────►│
  │                    │◄── tool schemas ───┤
  │◄── [Tool, Tool] ───┤                    │
  │                    │                    │
  │ invoke(tool, args) │                    │
  ├───────────────────►│ tools/call         │
  │                    ├───────────────────►│
  │                    │ (server executes)  │
  │                    │◄── result ─────────┤
  │◄── result ─────────┤                    │
```

### 3.4 Security Boundaries

- **Tool allowlists** per agent — agents cannot invoke tools outside their policy.
- **Argument validation** — every tool call passes
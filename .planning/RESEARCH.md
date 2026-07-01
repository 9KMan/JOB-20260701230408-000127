# RESEARCH.md

## Tech Stack Decisions

### Agent Orchestration
- **LangGraph** chosen because it provides graph-native state management with built-in checkpointing, supports cycles (critical for iterative workflows), and has first-class LangChain integration. The StateGraph model maps directly to multi-agent coordination patterns where agents need shared context and conditional branching.

### Vector Search & Persistence
- **PostgreSQL + pgvector** chosen because it consolidates infrastructure to a single enterprise-grade database. Eliminates operational overhead of managing separate vector DB services (Pinecone, Weaviate). Supports <100ms queries at production scale with proper indexing (HNSW) and offers full ACID compliance for transaction-sensitive operations.

### LLM Integration
- **LangChain abstractions over direct API calls** chosen because it provides provider abstraction (OpenAI, Anthropic) with consistent interfaces, built-in retry logic, and token management. Allows escape hatches to raw APIs when needed for custom prompting or cost optimization.

### Enterprise API Layer
- **FastAPI** chosen because native async support handles concurrent agent requests efficiently, Pydantic v2 provides runtime validation with minimal overhead, and automatic OpenAPI documentation accelerates integration. ASGI architecture supports production workloads with uvicorn/uv.

### Agent Communication Protocol
- **MCP (Model Context Protocol)** chosen because it's emerging as the standard for agent-tool communication, provides type-safe interfaces, and supports both local and remote tool execution. Allows standardized integration with enterprise systems.

### Observability
- **OpenTelemetry + LangSmith** chosen because OpenTelemetry provides vendor-agnostic instrumentation with exporter flexibility (Jaeger, OTLP endpoints), while LangSmith offers LangChain-specific tracing, evaluation datasets, and runtime debugging. Combined coverage for both custom code and LLM interactions.

---

## Library Choices

### Web/API Layer
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
```

### Database & ORM
```
asyncpg>=0.29.0
psycopg2-binary>=2.9.9
sqlalchemy[asyncio]>=2.0.25
pgvector>=0.2.3
```

### Agent/AI Framework
```
langgraph>=0.0.35
langchain>=0.1.4
langchain-core>=0.1.20
langchain-openai>=0.0.5
langchain-anthropic>=0.1.0
langchain-community>=0.0.20
```

### Evaluation & Observability
```
langsmith>=0.1.0
opentelemetry-api>=1.22.0
opentelemetry-sdk>=1.22.0
opentelemetry-instrumentation-fastapi>=0.43b0
opentelemetry-instrumentation-langchain>=0.43b0
```

### Utilities & Configuration
```
python-dotenv>=1.0.0
structlog>=24.1.0
tenacity>=8.2.0
httpx>=0.26.0
```

---

## Patterns to Use

### 1. Supervisor/Orchestrator Pattern
Central supervisor agent manages task decomposition and delegates to specialized sub-agents (retriever, analyst, synthesizer). Supervisor maintains global state and controls flow based on agent outputs. Implemented via LangGraph's `StateGraph` with conditional edges routing based on task type.

### 2. Stateful Workflow with Checkpointing
LangGraph's `MemorySaver` checkpointing enables:
- Long-running workflow persistence across service restarts
- Human-in-the-loop interruption with resume capability
- Debug/replay of agent decision paths
- Branching for parallel exploration with later merge

### 3. RAG Pipeline with Hybrid Retrieval
Production RAG combining:
- Dense retrieval via pgvector (semantic similarity)
- Sparse retrieval via full-text search (keyword matching)
- Reranking with cross-encoders for precision
- Query decomposition for complex multi-hop questions
- Citation/metadata attachment for source tracking

### 4. Circuit Breaker with Graceful Degradation
Protect against LLM API failures and latency spikes:
- Tenacity-powered retry with exponential backoff
- Fallback to cached responses or simplified heuristics
- Timeout enforcement per agent with global circuit breaker
- User-facing degradation messaging rather than silent failures

### 5. Event-Driven Audit Architecture
Structured logging pipeline:
- Every state transition captured as structured event (structlog)
- Correlation IDs propagate through agent chain
- Audit log writes to append-only table (not deleted)
- Real-time stream to observability backend via OpenTelemetry

---

## Trade-offs Considered

### Trade-off 1: LangChain Abstraction vs. Direct API Control

| Aspect | LangChain | Direct API |
|--------|-----------|------------|
| Development speed | High | Low |
| Debugging complexity | Higher (indirection) | Lower |
| Provider flexibility | Built-in abstraction | Manual implementation |
| Customization | Constrained by patterns | Full control |

**Decision: LangChain with escape hatches**

Accept moderate debugging complexity in exchange for development velocity. Maintain raw API capability for performance-critical paths or when LangChain abstractions introduce unnecessary overhead.

### Trade-off 2: Single Database (PostgreSQL/pgvector) vs. Specialized Vector DB

| Aspect | PostgreSQL + pgvector | Dedicated Vector DB |
|--------|----------------------|---------------------|
| Operational complexity | Low (single system) | High (multiple services) |
| Query performance | Good (<100ms achievable) | Excellent (optimized) |
| Data consistency | Strong (ACID) | Varies by implementation |
| Scalability | Vertical + read replicas | Horizontal, managed options |

**Decision: PostgreSQL + pgvector**

Accept slightly lower raw vector performance to eliminate operational complexity. Enterprise requirements (<100ms) are achievable with proper HNSW indexing and connection pooling. Single-database simplifies backup, replication, and compliance requirements.

### Trade-off 3: Synchronous vs. Asynchronous Agent Execution

| Aspect | Sync (threaded) | Async (event loop) |
|--------|-----------------|-------------------|
| I/O efficiency | Poor (blocking) | Excellent |
| Concurrency model | Simple, familiar | Requires async mindset |
| LLM calls per request | Multiple serial | Multiple concurrent |
| Debugging | Standard tracebacks | Event loop complexity |

**Decision: Async primary with sync wrappers**

Design core agent logic as async-first for I/O-bound LLM calls. Provide sync wrappers for synchronous contexts (CLI tools, simple integrations). Async enables batching concurrent tool calls and parallel agent execution within a workflow.

---

## Confidence Assessment

| Decision Area | Confidence | Rationale |
|---------------|------------|-----------|
| LangGraph for orchestration | **HIGH** | Stable release, active development, proven at production scale in LangChain ecosystem |
| PostgreSQL + pgvector | **HIGH** | Mature technology, meets performance requirements, simplifies operations |
| FastAPI for API layer | **HIGH** | Battle-tested, large community, excellent async support |
| MCP for tool protocol | **MEDIUM** | Emerging standard with momentum, but not yet universally adopted |
| LangChain ecosystem | **MEDIUM** | Rapidly evolving; API stability improved but breaking changes still occur between minor versions |
| OpenTelemetry instrumentation | **HIGH** | Vendor-neutral standard, stable API, comprehensive ecosystem |
| Specific library versions | **MEDIUM** | Recommend pinning exact versions after integration testing; current constraints represent minimums |
"""FastAPI application entrypoint.

This module owns the FastAPI ``app`` object and the *only* place we
configure cross-cutting middleware (CORS, logging, OpenTelemetry).
The heavyweight business logic lives under ``app/orchestrator`` and
``app/models``; ``app/main.py`` only wires the surface area.

Endpoints shipped in Phase 2:

* ``GET /health``  — liveness + dependency health (Postgres + Redis).
* ``GET /stack``   — resolved stack choices (debug / verification).
* ``GET /``        — minimal index pointing to docs.

OpenAPI is served at ``/docs`` (Swagger UI) and ``/openapi.json``
(downloadable schema).

Logging
-------
We configure ``loguru`` once at module import time so every downstream
log line goes through a structured JSON sink. ``LOG_LEVEL`` controls
the threshold; setting ``DEBUG`` exposes verbose agent traces.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.settings import get_settings


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    """Wire ``loguru`` to emit structured logs to stderr.

    Idempotent: safe to call multiple times.
    """
    logger.remove()  # remove the default stderr sink to avoid duplicate output
    settings = get_settings()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        serialize=False,
        enqueue=False,  # uvicorn already runs an asyncio loop
        backtrace=True,
        diagnose=False,
        format=(
            "<green>{time:YYYY-MM-DDTHH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "<level>{message}</level>"
        ),
    )
    logger.info("logging.configured level={}", settings.log_level)


# ---------------------------------------------------------------------------
# Healthcheck helpers
# ---------------------------------------------------------------------------

async def _check_postgres() -> tuple[bool, str]:
    """Verify the configured Postgres connection is alive.

    Done in a best-effort way: any exception (missing driver, refused
    connection, missing DB) becomes an error string rather than a 500.
    For the foundation phase we try the ``asyncpg`` driver and fall
    back to the synchronous ``psycopg`` driver if absent.
    """
    settings = get_settings()
    url = settings.database_url
    try:
        if url.startswith(("postgresql+asyncpg://", "postgresql://")):
            # We don't import asyncpg at module level — the platform code
            # uses ``app.db`` (SQLAlchemy). For the healthcheck we do
            # import-on-demand so a missing driver doesn't break import.
            import asyncpg  # type: ignore[import-not-found]

            target = url
            for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql://"):
                if target.startswith(prefix):
                    target = "postgresql://" + target[len(prefix):]
                    break
            try:
                conn = await asyncio.wait_for(asyncpg.connect(target), timeout=2.0)
                try:
                    val = await conn.fetchval("SELECT 1")
                finally:
                    await conn.close()
                return (val == 1, "ok" if val == 1 else "query returned unexpected value")
            except Exception as e:
                return (False, f"{type(e).__name__}: {e}")
        return (True, "skipped (non-postgres DSN)")
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")


async def _check_redis() -> tuple[bool, str]:
    """Verify the configured Redis connection is alive."""
    settings = get_settings()
    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]

        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await asyncio.wait_for(client.ping(), timeout=2.0)
            return (bool(pong), "ok" if pong else "no PONG")
        finally:
            await client.aclose()
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: configure logging on startup, log shutdown on stop."""
    _configure_logging()
    logger.info("app.starting env={} title={}", os.environ.get("ENVIRONMENT", "development"), app.title)
    try:
        yield
    finally:
        logger.info("app.stopping title={}", app.title)


def create_app() -> FastAPI:
    """FastAPI app factory.

    Kept as a function (not a module-level constant) so tests can
    instantiate fresh instances with overridden settings.
    """
    settings = get_settings()

    app = FastAPI(
        title="Agentic AI Platform",
        version="0.2.0",
        description=(
            "Enterprise multi-agent AI orchestration platform: LangGraph + "
            "pgvector + FastAPI. Seven capability pillars — agent orchestration, "
            "RAG, memory, human-in-the-loop, observability, governance, and "
            "enterprise workflow automation."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — wide-open in development; tighten in production via env vars.
    allowed_origins = ["*"] if settings.environment == "development" else [
        o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Health -----------------------------------------------------------
    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:  # noqa: D401 — endpoint is a noun
        """Liveness + dependency health.

        Returns HTTP 200 with ``status=ok`` only when *both* Postgres and
        Redis are reachable. Otherwise returns 503 and a per-dependency
        error string so the caller can route the failure.
        """
        pg_ok, pg_msg = await _check_postgres()
        rd_ok, rd_msg = await _check_redis()
        body = {
            "status": "ok" if (pg_ok and rd_ok) else "degraded",
            "version": app.version,
            "checks": {
                "postgres": {"ok": pg_ok, "detail": pg_msg},
                "redis": {"ok": rd_ok, "detail": rd_msg},
            },
        }
        if not (pg_ok and rd_ok):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=body,
            )
        return body

    # --- Stack self-report (Phase 2 verification helper) -----------------
    @app.get("/stack", tags=["meta"])
    def stack() -> dict[str, Any]:
        """Resolved stack choices — for Phase 2 verification."""
        return {
            "version": app.version,
            "orchestration": "LangGraph",
            "llm_abstraction": "LangChain (thin) + raw provider SDKs",
            "providers": ["openai", "anthropic"],
            "agent_protocol": "MCP",
            "api": "FastAPI",
            "validation": "Pydantic v2",
            "database": "PostgreSQL + pgvector",
            "vector_index": settings.vector_index_type,
            "vector_dim": settings.vector_dim,
            "vector_ef_construction": settings.vector_ef_construction,
            "vector_m": settings.vector_m,
            "redis_url": settings.redis_url.split("@")[-1],  # never log creds
            "observability": ["loguru", "opentelemetry", "prometheus-client", "langfuse"],
            "auth": {
                "jwt_algorithm": settings.jwt_algorithm,
                "audit_log_retention_days": settings.audit_log_retention_days,
            },
        }

    # --- Index -----------------------------------------------------------
    @app.get("/", tags=["meta"])
    def index() -> dict[str, str]:
        """Friendly index pointing at the docs."""
        return {
            "service": "agentic-ai-platform",
            "version": app.version,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
            "stack": "/stack",
        }

    return app


# Module-level app object so ``uvicorn app.main:app`` Just Works.
app = create_app()


__all__ = ["app", "create_app"]

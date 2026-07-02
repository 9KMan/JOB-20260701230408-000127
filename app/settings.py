"""Pydantic v2 settings — typed configuration loaded from environment.

The :class:`Settings` class is the single source of truth for every
runtime knob:

* LLM provider credentials (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
* PostgreSQL/pgvector connection strings and pool sizing.
* Vector index configuration (dim, HNSW parameters).
* Redis connection.
* API server settings.
* Log level and observability.

All values are typed (Pydantic v2 ``BaseSettings``) so a typo in an env
var fails fast at startup rather than as a runtime ``KeyError``.

The :func:`get_settings` factory is memoised with :func:`functools.lru_cache`
so importing this module is cheap and the configuration object is a
process-level singleton.

Usage::

    from app.settings import get_settings
    s = get_settings()
    print(s.database_url)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime configuration for the agentic AI platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # LLM Providers
    # ------------------------------------------------------------------
    # Required in production; defaults are non-secret placeholders for
    # local-dev import convenience. If you actually call an LLM without
    # real keys, you'll get an auth error from the provider, which is the
    # correct behaviour.
    openai_api_key: str = Field(default="sk-not-set", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="sk-ant-not-set", alias="ANTHROPIC_API_KEY")

    # ------------------------------------------------------------------
    # Database (PostgreSQL + pgvector)
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://agentic:agentic_dev@localhost:5432/agentic_platform",
        alias="DATABASE_URL",
        description="Async DSN (asyncpg driver) used by the orchestrator.",
    )
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE", ge=1, le=200)
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW", ge=0, le=200)

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------
    vector_dim: int = Field(default=1536, alias="VECTOR_DIM", ge=64, le=8192)
    vector_index_type: Literal["hnsw", "ivfflat"] = Field(
        default="hnsw", alias="VECTOR_INDEX_TYPE"
    )
    vector_ef_construction: int = Field(
        default=64, alias="VECTOR_EF_CONSTRUCTION", ge=8, le=1024
    )
    vector_m: int = Field(default=16, alias="VECTOR_M", ge=2, le=128)

    # ------------------------------------------------------------------
    # Redis (task broker + working-memory cache)
    # ------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
        description="Redis URL for broker + cache.",
    )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT", ge=1, le=65535)
    api_workers: int = Field(default=4, alias="API_WORKERS", ge=1, le=64)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    environment: Literal["development", "staging", "production", "test"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", alias="LANGFUSE_HOST"
    )

    # ------------------------------------------------------------------
    # Governance / auth (Phase 7 surfaces these as required)
    # ------------------------------------------------------------------
    jwt_secret: str = Field(
        default="x" * 48,  # safe placeholder for local dev
        alias="JWT_SECRET",
        min_length=32,
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    audit_log_retention_days: int = Field(
        default=365, alias="AUDIT_LOG_RETENTION_DAYS", ge=1, le=3650
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        # Accept the documented drivers; reject obviously-broken DSNs.
        if not (
            v.startswith("postgresql://")
            or v.startswith("postgresql+")
            or v.startswith("sqlite://")
            or v.startswith("sqlite+")
        ):
            raise ValueError(
                f"DATABASE_URL must use postgresql:// or sqlite:// (got: {v[:32]}…)"
            )
        return v

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, v: str) -> str:
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-singleton :class:`Settings`.

    ``@lru_cache`` means a fresh :class:`Settings` is constructed only
    on the first call; subsequent calls reuse the cached object. This
    is fine for our process model — configuration does not change at
    runtime — and avoids the cost of re-reading + re-validating env vars
    on every access.

    For tests that need to swap configuration, call
    :func:`get_settings.cache_clear` and re-call with mutated env vars.
    """
    s = Settings()  # type: ignore[call-arg]
    logger.debug(
        "settings.loaded env={} api_host={} api_port={} vector_dim={} index={} db={}",
        s.environment,
        s.api_host,
        s.api_port,
        s.vector_dim,
        s.vector_index_type,
        _redact_dsn(s.database_url),
    )
    return s


def _redact_dsn(dsn: str) -> str:
    """Redact credentials from a DSN before logging."""
    if "@" in dsn and "://" in dsn:
        scheme, rest = dsn.split("://", 1)
        if "@" in rest:
            _, host_part = rest.split("@", 1)
            return f"{scheme}://***@{host_part}"
    return dsn


__all__ = ["Settings", "get_settings"]

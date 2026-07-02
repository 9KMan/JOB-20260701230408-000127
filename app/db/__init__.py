"""Database layer — async SQLAlchemy engine + session factory.

This package provides the low-level database plumbing used by the
orchestrator. We use SQLAlchemy 2.0's async API throughout.

The engine and session factory are created lazily (on first call to
:meth:`get_engine` / :meth:`get_session_factory`) so that importing
this module is cheap and side-effect-free.

Configuration is read from environment variables:

* ``DATABASE_URL`` — full async DSN (e.g.
  ``postgresql+asyncpg://user:pass@host:5432/db``). When unset, we
  fall back to a SQLite in-memory database so unit tests can run
  without a real Postgres instance.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

__all__ = [
    "Base",
    "get_engine",
    "get_session_factory",
    "session_scope",
    "reset_engine",
]


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_url(url: str) -> str:
    """Convert sync DSNs to async DSNs in-place.

    ``postgresql://`` becomes ``postgresql+asyncpg://`` and
    ``sqlite://`` becomes ``sqlite+aiosqlite://``. Used so that a
    single env var works for both sync tools (alembic) and the
    async orchestrator.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


def get_database_url() -> str:
    """Return the active database URL (env var or test default)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return _normalize_url(url)
    # Default to in-memory SQLite for unit tests. Production must set
    # DATABASE_URL to a real PostgreSQL DSN.
    return "sqlite+aiosqlite:///:memory:"


def get_engine() -> AsyncEngine:
    """Return the lazily-initialized global :class:`AsyncEngine`."""
    global _engine
    if _engine is None:
        url = get_database_url()
        # echo=False keeps logs quiet; flip via DATABASE_ECHO=1 in dev.
        echo = os.environ.get("DATABASE_ECHO", "0") == "1"
        _engine = create_async_engine(url, echo=echo, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the lazily-initialized session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager that yields an :class:`AsyncSession`.

    Commits on a clean exit, rolls back on exception. Closes the
    session in all cases.

    Example::

        async with session_scope() as session:
            result = await session.execute(select(Task))
            ...
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def create_all() -> None:
    """Create all tables (test helper).

    Uses ``Base.metadata.create_all`` against the configured engine.
    Production deployments should use Alembic migrations instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all() -> None:
    """Drop all tables (test helper)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def reset_engine() -> None:
    """Dispose of the cached engine and session factory.

    Useful in tests that swap the ``DATABASE_URL`` between cases.
    """
    global _engine, _session_factory
    if _engine is not None:
        # Best-effort dispose; if the loop is closed we ignore it.
        try:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule dispose and return; can't await here.
                    loop.create_task(_engine.dispose())
                else:
                    loop.run_until_complete(_engine.dispose())
            except RuntimeError:
                pass
        except Exception:
            pass
    _engine = None
    _session_factory = None
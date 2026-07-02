#!/usr/bin/env python3
"""Phase 2 verification — prove every chosen library imports and resolves.

Run::

    python scripts/verify_stack.py

Exits ``0`` when **all** modules listed in ``REQUIRED`` import cleanly;
exits ``1`` otherwise. Prints a final summary line:

    Stack: N/N components importable

so CI logs can grep for the result without parsing tables.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from typing import Iterable

# ---------------------------------------------------------------------------
# The contract: every component that appears in pyproject.toml must import.
#
# These map 1:1 to the dependency blocks in pyproject.toml. If you add a
# dependency to pyproject.toml, also add it here. If you remove one, also
# remove it here.
# ---------------------------------------------------------------------------
REQUIRED: dict[str, str] = {
    # -- Orchestration (LangGraph)
    "langgraph": "LangGraph (graph-native orchestration)",
    "langgraph.graph": "LangGraph graph API",
    "langgraph.checkpoint": "LangGraph checkpointing primitives",
    # -- LLM providers
    "openai": "OpenAI SDK",
    "anthropic": "Anthropic SDK",
    # -- Persistence + vectors
    "sqlalchemy": "SQLAlchemy ORM + async",
    "sqlalchemy.ext.asyncio": "SQLAlchemy async API",
    "asyncpg": "asyncpg (Postgres async driver)",
    "psycopg": "psycopg 3 (Postgres sync driver, used by Alembic)",
    "pgvector": "pgvector Python bindings",
    # -- API layer
    "fastapi": "FastAPI",
    "pydantic": "Pydantic v2 core",
    "pydantic_settings": "Pydantic Settings",
    "uvicorn": "Uvicorn ASGI server",
    # -- Redis (broker + cache)
    "redis": "Redis client",
    "redis.asyncio": "Redis async client",
    # -- Observability + logging
    "loguru": "loguru structured logging",
}


def _safe_import(name: str) -> tuple[bool, str, str]:
    """Try to import ``name``. Returns ``(ok, version, error_str)``."""
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", None)
        if version is None:
            # Some sub-modules have no __version__; report their top-level.
            top = name.split(".", 1)[0]
            try:
                top_mod = importlib.import_module(top)
                version = getattr(top_mod, "__version__", "n/a")
            except Exception:
                version = "n/a"
        return True, str(version), ""
    except Exception as e:  # pragma: no cover — exercised by error test
        return False, "n/a", f"{type(e).__name__}: {e}"


def verify(modules: Iterable[tuple[str, str]] | None = None) -> tuple[int, int, list[str]]:
    """Run the import verification.

    Returns ``(imported, total, failed_list)`` so the caller can format
    output however they want.
    """
    items = list(modules) if modules is not None else list(REQUIRED.items())
    imported = 0
    failed: list[str] = []
    for mod_name, label in items:
        ok, version, err = _safe_import(mod_name)
        marker = "OK  " if ok else "FAIL"
        version_str = version if ok else err
        print(f"{marker} {label:50s} {mod_name:35s} {version_str}")
        if ok:
            imported += 1
        else:
            failed.append(mod_name)
    return imported, len(items), failed


def main() -> int:
    imported, total, failed = verify()
    print()
    if failed:
        print(f"FAILED modules: {', '.join(failed)}")
    print(f"Stack: {imported}/{total} components importable")
    # Exit 0 only when everything imported.
    return 0 if not failed else 1


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)

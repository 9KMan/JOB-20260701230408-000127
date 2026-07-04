"""Pytest version of the stack-import verification.

The runnable smoke check is ``scripts/verify_stack.py``; this file is its
``pytest``-shape equivalent so it integrates with CI. Each component
in the curated stack gets its own parametrised test, plus a small set
of *behavioural* sanity tests (``test_pydantic_v2``,
``test_fastapi_app_boots``, ``test_settings_load``) that go one step
beyond importability — they assert the component is actually usable.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# Make ``app`` importable when this file is run directly (e.g. ``pytest`` from
# repo root). The installed package would normally expose this, but until
# ``pip install -e .`` has run, we help pytest find it.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Parametrised per-component import tests
# ---------------------------------------------------------------------------
COMPONENTS: list[str] = [
    # Orchestration
    "langgraph",
    "langgraph.graph",
    "langgraph.checkpoint",
    # LLM providers
    "openai",
    "anthropic",
    # Persistence + vectors
    "sqlalchemy",
    "sqlalchemy.ext.asyncio",
    "asyncpg",
    "psycopg",
    "pgvector",
    # API layer
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "uvicorn",
    # Redis
    "redis",
    "redis.asyncio",
    # Logging
    "loguru",
]


@pytest.mark.parametrize("module_name", COMPONENTS)
def test_import(module_name: str) -> None:
    """Every stack component listed in pyproject.toml must import."""
    mod = importlib.import_module(module_name)
    assert mod is not None, f"import returned None for {module_name}"


# ---------------------------------------------------------------------------
# Behavioural sanity checks
# ---------------------------------------------------------------------------


def test_pydantic_v2() -> None:
    """Confirm Pydantic v2 (not v1) is installed and the v2 API works."""
    import pydantic

    major = int(pydantic.VERSION.split(".")[0])
    assert major >= 2, f"Expected Pydantic v2; got {pydantic.VERSION}"

    from pydantic import BaseModel

    class M(BaseModel):
        x: int
        name: str = "default"

    # v2 marker: ``model_validate`` and ``model_dump``
    assert hasattr(BaseModel, "model_validate")
    assert hasattr(BaseModel, "model_dump")
    assert hasattr(M, "model_json_schema")
    # Round-trip
    obj = M.model_validate({"x": 7})
    assert obj.x == 7
    assert obj.name == "default"
    assert M.model_validate(M.model_dump(obj)) == obj


def test_pydantic_settings_works() -> None:
    """Pydantic Settings must read from the environment."""
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    os.environ.setdefault("JWT_SECRET", "x" * 48)
    from app.settings import get_settings

    # Clear cached settings so we re-read env.
    get_settings.cache_clear()
    s = get_settings()
    assert s.api_port >= 1
    assert s.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    # Restore cache so later tests get a clean default.
    get_settings.cache_clear()


def test_settings_load() -> None:
    """``app.settings.Settings`` instantiates from env vars with sane defaults."""
    # Ensure deterministic defaults — we set (not setdefault) so the
    # test is independent of any earlier test that may have set a
    # SQLite fallback URL.
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://x:y@h:5432/d"
    os.environ["JWT_SECRET"] = "x" * 48
    os.environ["VECTOR_DIM"] = "1536"
    os.environ["VECTOR_INDEX_TYPE"] = "hnsw"
    from app.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.vector_dim == 1536
    assert s.vector_index_type == "hnsw"
    assert s.vector_ef_construction >= 8
    assert s.vector_m >= 2
    assert s.database_url.startswith("postgresql")
    assert s.redis_url.startswith("redis")
    get_settings.cache_clear()


def test_fastapi_app_boots() -> None:
    """``app.main.app`` exists, has the expected title, and exposes /health."""
    from app.main import app

    assert app.title == "Agentic AI Platform"
    assert app.version
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/health" in routes, f"/health not in routes: {routes}"
    assert "/stack" in routes, f"/stack not in routes: {routes}"
    # OpenAPI doc paths are configurable in FastAPI; we configured /docs.
    assert any(p.endswith("/docs") or p.endswith("docs") for p in routes)


def test_settings_singleton_memoised() -> None:
    """``get_settings()`` returns the same object on repeated calls."""
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    os.environ.setdefault("JWT_SECRET", "x" * 48)
    from app.settings import get_settings

    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b, "get_settings() should memoise the Settings instance"


def test_verify_stack_script_module() -> None:
    """The ``scripts/verify_stack.py`` module is importable and exposes ``REQUIRED``."""
    import importlib.util
    from pathlib import Path

    script = REPO_ROOT / "scripts" / "verify_stack.py"
    assert script.is_file(), f"{script} missing"

    spec = importlib.util.spec_from_file_location("verify_stack_script", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    assert hasattr(mod, "REQUIRED"), "verify_stack.py must define REQUIRED"
    assert hasattr(mod, "verify"), "verify_stack.py must define verify()"
    assert hasattr(mod, "main"), "verify_stack.py must define main()"


def test_verify_stack_returns_n_over_n_when_clean() -> None:
    """The verify_stack helper imports every declared component."""
    from scripts.verify_stack import verify  # type: ignore[import-not-found]

    imported, total, failed = verify()
    assert total > 0, "REQUIRED must declare at least one component"
    assert imported == total, (
        f"Expected {total}/{total} importable, got {imported}/{total}; "
        f"failed={failed}"
    )

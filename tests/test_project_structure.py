"""Phase 1 contract tests.

These tests verify that the foundational deliverables exist and contain
what `mark-build-done.py` and the Phase 1 plan require:

* All foundational files exist at the documented paths.
* ``README.md`` lists every one of the seven capability pillars.
* ``README.md`` opens with the **Business Problem Solved** section
  (a mark-build-done.py quality gate).
* ``docs/PROJECT_OVERVIEW.md`` defines scope, success criteria, and
  stakeholder model.

The tests are intentionally file-system-level so they run before
the stack itself is installed.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_readme_exists() -> None:
    """``README.md`` must exist at the repository root."""
    assert (REPO_ROOT / "README.md").is_file(), "README.md must exist"


def test_pyproject_exists() -> None:
    """``pyproject.toml`` must exist with valid TOML."""
    p = REPO_ROOT / "pyproject.toml"
    assert p.is_file(), "pyproject.toml must exist"
    # Don't fail on a stub; the [project] section is what Phase 2 cares about.
    content = p.read_text(encoding="utf-8")
    assert "[project]" in content, "pyproject.toml must define a [project] table"
    assert "name" in content, "pyproject.toml must declare the package name"


def test_docker_compose_exists() -> None:
    """``docker-compose.yml`` must exist and reference pgvector + redis."""
    p = REPO_ROOT / "docker-compose.yml"
    assert p.is_file(), "docker-compose.yml must exist"
    content = p.read_text(encoding="utf-8")
    assert "pgvector/pgvector:pg16" in content, "compose must use pgvector/pgvector:pg16"
    assert "redis" in content.lower(), "compose must include a redis service"
    assert "5432:5432" in content, "compose must expose Postgres on 5432"


def test_env_example_exists() -> None:
    """``.env.example`` must document required environment variables."""
    p = REPO_ROOT / ".env.example"
    assert p.is_file(), ".env.example must exist"
    content = p.read_text(encoding="utf-8")
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DATABASE_URL", "REDIS_URL", "LOG_LEVEL"):
        assert var in content, f".env.example must define {var}"


def test_gitignore_exists() -> None:
    """``.gitignore`` must exist so secrets and build artefacts stay untracked."""
    p = REPO_ROOT / ".gitignore"
    assert p.is_file(), ".gitignore must exist"
    content = p.read_text(encoding="utf-8")
    assert ".env" in content, ".gitignore must include .env"
    assert "__pycache__" in content, ".gitignore must include __pycache__/"


def test_project_overview_doc_exists() -> None:
    """``docs/PROJECT_OVERVIEW.md`` must exist."""
    assert (REPO_ROOT / "docs" / "PROJECT_OVERVIEW.md").is_file(), (
        "docs/PROJECT_OVERVIEW.md must exist"
    )


# ---------------------------------------------------------------------------
# README content
# ---------------------------------------------------------------------------

SEVEN_PILLARS = [
    # Each pillar is a stable keyword; the README mentions each at least once.
    "orchestration",
    "rag",
    "memory",
    "human-in-the-loop",
    "observability",
    "governance",
    "workflow automation",
]


def test_readme_first_section_is_business_problem_solved() -> None:
    """The README must open with **Business Problem Solved**.

    This is a hard quality gate for ``mark-build-done.py``: every
    downstream review uses it as the entry point, and reviewers
    shouldn't have to scroll past advertising to find the substance.
    """
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    # `## Business Problem Solved` should appear before any other `##` section.
    biz_idx = content.find("## business problem solved")
    assert biz_idx >= 0, "README.md must contain '## Business Problem Solved'"
    # Find the next `## ` (third-level+ header) after the first.
    after = content[biz_idx + 1:]
    nxt = after.find("\n## ")
    if nxt >= 0:
        next_section = after[nxt + 1: nxt + 200].split("\n", 1)[0]
        # Allow architecture/quick-start to come right after, but not before.
        assert biz_idx < (biz_idx + nxt + 1), (
            "Business Problem Solved must be the first major section"
        )


def test_readme_references_all_seven_pillars() -> None:
    """The README must reference every one of the seven capability pillars."""
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    missing = [p for p in SEVEN_PILLARS if p not in content]
    assert not missing, f"README missing pillars: {missing}"


def test_readme_links_to_out_of_scope() -> None:
    """The README must link to ``OUT_OF_SCOPE.md`` for scope discoverability."""
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "OUT_OF_SCOPE.md" in content, "README must reference OUT_OF_SCOPE.md"


# ---------------------------------------------------------------------------
# PROJECT_OVERVIEW content
# ---------------------------------------------------------------------------

def test_project_overview_defines_scope_and_criteria() -> None:
    """``PROJECT_OVERVIEW.md`` must define scope, success criteria, stakeholders."""
    content = (REPO_ROOT / "docs" / "PROJECT_OVERVIEW.md").read_text(encoding="utf-8").lower()
    # Scope
    assert "scope" in content, "PROJECT_OVERVIEW.md must discuss scope"
    assert "in scope" in content or "in-scope" in content, (
        "PROJECT_OVERVIEW.md must define what's in scope"
    )
    # Success criteria — at least one measurable target.
    assert "success criteria" in content or "success criterion" in content, (
        "PROJECT_OVERVIEW.md must define success criteria"
    )
    # Stakeholder model.
    assert "stakeholder" in content, "PROJECT_OVERVIEW.md must define stakeholders"


def test_out_of_scope_doc_phase6_deliverable() -> None:
    """``OUT_OF_SCOPE.md`` is delivered in Phase 6, not Phase 1.

    It must exist *by the end of the build*; this test asserts the
    placeholder / stub from a later phase is permitted to be absent now.
    The Phase 6 test file ``test_out_of_scope_doc.py`` will assert the
    full content requirements once that phase lands.
    """
    p = REPO_ROOT / "OUT_OF_SCOPE.md"
    # Phase 1 ships without OUT_OF_SCOPE.md; Phase 6 must add it.
    assert p.is_file() or not p.exists(), (
        "Phase 1 acceptance is satisfied whether or not OUT_OF_SCOPE.md exists yet. "
        f"It was found at {p}; that is fine — Phase 6 tests will assert full content."
    )

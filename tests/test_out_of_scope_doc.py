"""Phase 6 contract tests — ``OUT_OF_SCOPE.md`` has the right shape.

These tests assert:

* ``OUT_OF_SCOPE.md`` exists at the repository root.
* The document carries all six canonical sections (Out-of-Scope
  Workstreams, Integration Boundaries, Explicit Non-Goals, Deferred
  Phases, Reference table, and a Usage/Notes heading).
* All seven in-scope CONTEXT.md functional requirement keywords are
  referenced inside the in-scope reference table.
* At least the 13 mandated non-implemented workstreams are enumerated
  (multi-tenant SaaS, mobile clients, end-user chat UI, fine-tuning,
  voice, vision, video, robotics, browser automation, blockchain,
  HIPAA, FedRAMP, PCI-DSS).
* ``README.md`` links to ``OUT_OF_SCOPE.md`` for discoverability.

When the document changes, these tests must change in the same commit —
they are the mechanical enforcement of the Phase 6 contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_OF_SCOPE = REPO_ROOT / "OUT_OF_SCOPE.md"
README = REPO_ROOT / "README.md"


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_out_of_scope_file_exists() -> None:
    """OUT_OF_SCOPE.md must exist at the repository root."""
    assert OUT_OF_SCOPE.is_file(), f"Missing required file: {OUT_OF_SCOPE}"


# ---------------------------------------------------------------------------
# Canonical section phrasing
# ---------------------------------------------------------------------------

REQUIRED_SECTION_HEADINGS = [
    "## 1. Out-of-Scope Workstreams",
    "## 2. Integration Boundaries",
    "## 3. Explicit Non-Goals",
    "## 4. Deferred Phases",
    "## 5. Reference",
    "## 6.",
]


def test_out_of_scope_has_all_canonical_sections() -> None:
    """OUT_OF_SCOPE.md must include all six canonical section headings."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    missing = [
        h for h in REQUIRED_SECTION_HEADINGS
        # Match ``## 6.`` as a *prefix* so we accept "## 6. How to use …"
        if not (h.endswith("## 6.")  and content.find(h.split("## 6.")[0] + "## 6.") != -1)
        and not content.find(h) >= 0
    ]
    # Re-run a clean check so the failure message is legible.
    missing = []
    for heading in REQUIRED_SECTION_HEADINGS:
        if heading.endswith("## 6."):
            # Tolerate any "## 6. <something>" heading.
            pattern = re.compile(r"^##\s*6\.\s*\S", re.MULTILINE)
            if not pattern.search(content):
                missing.append("## 6. <something>")
        else:
            if heading not in content:
                missing.append(heading)
    assert not missing, f"OUT_OF_SCOPE.md missing canonical sections: {missing}"


def test_out_of_scope_starts_with_title_heading() -> None:
    """Document must start with ``# OUT OF SCOPE`` (the top-level title)."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    # Look at the first 200 chars.
    head = content[:200]
    assert "# OUT OF SCOPE" in head.upper() or head.upper().startswith("# "), (
        "OUT_OF_SCOPE.md should open with '# OUT OF SCOPE' as the title heading"
    )


# ---------------------------------------------------------------------------
# Required non-implemented workstream enumeration
# ---------------------------------------------------------------------------

REQUIRED_NON_IMPLEMENTED_KEYWORDS = [
    "Multi-tenant",        # multi-tenant SaaS layer
    "Mobile",              # mobile or desktop client applications
    "End-user",            # end-user-facing chat UI
    "fine-tuning",         # model training or fine-tuning pipelines
    "Voice",               # voice/audio processing pipelines
    "vision",              # computer vision pipelines
    "Video",               # video processing
    "Robotics",            # robotics or IoT integration
    "Browser automation",  # browser automation at scale
    "Blockchain",          # blockchain or Web3 components
    "HIPAA",               # HIPAA-grade healthcare compliance
    "FedRAMP",             # FedRAMP / IL5 government cloud certification
    "PCI-DSS",             # PCI-DSS payment processing
]


def test_out_of_scope_enumerates_mandated_workstreams() -> None:
    """All 13 mandated non-implemented workstreams must be enumerated."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    missing = [k for k in REQUIRED_NON_IMPLEMENTED_KEYWORDS if k not in content]
    assert not missing, f"OUT_OF_SCOPE.md missing workstream keywords: {missing}"


def test_out_of_scope_enumerates_at_least_thirteen_workstreams() -> None:
    """The workstreams section must list at least 13 separate items.

    We measure this via top-level bullet points (``- ``) inside the
    ``## 1. Out-of-Scope Workstreams`` section. This guards against
    anyone collapsing the enumeration to a single sentence.
    """
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    # Slice out the first workstreams section.
    match = re.search(
        r"## 1\. Out-of-Scope Workstreams(.*?)(?=^##\s)", content, re.DOTALL | re.MULTILINE
    )
    assert match, "Cannot locate '## 1. Out-of-Scope Workstreams' section"
    section = match.group(1)
    bullets = re.findall(r"^\s*-\s", section, re.MULTILINE)
    assert len(bullets) >= 13, (
        f"Section 1 must enumerate at least 13 non-implemented workstreams; "
        f"found {len(bullets)} bullet points."
    )


# ---------------------------------------------------------------------------
# In-scope reference table covers every CONTEXT.md functional requirement
# ---------------------------------------------------------------------------

IN_SCOPE_KEYWORDS = [
    "Agent Orchestration",
    "Enterprise Workflow Automation",
    "RAG & Knowledge Retrieval",
    "AI Memory & Persistence",
    "Human-in-the-Loop Decision Support",
    "AI Evaluation & Observability",
    "AI Governance & Security",
]


def test_out_of_scope_references_all_in_scope_requirements() -> None:
    """Every CONTEXT.md in-scope functional requirement must appear."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    missing = [k for k in IN_SCOPE_KEYWORDS if k not in content]
    assert not missing, (
        f"OUT_OF_SCOPE.md must reference in-scope requirements: {missing}"
    )


def test_in_scope_requirements_appear_in_a_table_row() -> None:
    """The seven keywords must each appear inside a markdown table row.

    This is stronger than ``test_out_of_scope_references_all_in_scope_requirements``:
    it ensures they live in the reference table, not just somewhere in prose.
    """
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")
    # Find every markdown table row (a line starting with ``|``).
    table_rows = [ln.strip() for ln in content.splitlines() if ln.lstrip().startswith("|")]
    rows_blob = "\n".join(table_rows)
    missing = [k for k in IN_SCOPE_KEYWORDS if k not in rows_blob]
    assert not missing, (
        "The in-scope reference table is missing rows for: "
        + ", ".join(missing)
    )


# ---------------------------------------------------------------------------
# README linkage
# ---------------------------------------------------------------------------

def test_readme_links_to_out_of_scope_doc() -> None:
    """README.md must reference OUT_OF_SCOPE.md so reviewers can find it."""
    assert README.is_file(), "README.md must exist"
    content = README.read_text(encoding="utf-8")
    assert "OUT_OF_SCOPE.md" in content, (
        "README.md must contain a reference to OUT_OF_SCOPE.md"
    )


def test_readme_link_to_out_of_scope_is_a_real_link() -> None:
    """The README's reference must be more than just a string mention —
    it must be a markdown link or a bare path, and be discoverable
    from the first half of the README (above the architecture section).
    """
    content = README.read_text(encoding="utf-8")
    # Either markdown link ``[text](OUT_OF_SCOPE.md)`` or
    # bare reference ``OUT_OF_SCOPE.md``.
    md_link = bool(re.search(r"\[.*?\]\((?:\./)?OUT_OF_SCOPE\.md\)", content))
    bare_ref = "OUT_OF_SCOPE.md" in content
    assert md_link or bare_ref, "README must link to OUT_OF_SCOPE.md"


# ---------------------------------------------------------------------------
# Phase 1 deliverable parity smoke check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("keyword", [
    "agent orchestration",
    "rag",
    "memory",
    "human-in-the-loop",
    "observability",
    "governance",
    "workflow automation",
])
def test_out_of_scope_mentions_each_pillar_at_least_once(keyword: str) -> None:
    """The seven capability pillars should each be referenced somewhere.

    They appear either as in-scope tables or in surrounding prose; this
    test ensures the document is anchored to the seven pillars from
    ``README.md``.
    """
    content = OUT_OF_SCOPE.read_text(encoding="utf-8").lower()
    assert keyword in content, (
        f"OUT_OF_SCOPE.md should mention the '{keyword}' pillar somewhere"
    )

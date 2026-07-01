## Phase Goal
Explicitly document what is NOT included in this build to set clear scope boundaries for clients and reviewers.

## Files to Create

```file:OUT_OF_SCOPE.md
# OUT OF SCOPE

This document explicitly enumerates what is **not** included in this build. Setting clear boundaries prevents scope creep, protects client expectations, and helps reviewers evaluate what was actually delivered against what was deliberately deferred.

---

## 1. Out-of-Scope Workstreams

### 1.1 Not Implemented in This Build

The following workstreams are out of scope for the current engagement and would require separate work agreements:

- **Multi-tenant SaaS layer**: No tenant isolation, per-tenant encryption keys, or billing/metering systems. The build assumes a single organizational tenant with internal access controls only.

- **Mobile or desktop client applications**: This build is a server-side platform with HTTP/WebSocket APIs only. No React Native, Swift, Kotlin, Electron, or PWA client work.

- **End-user-facing chat UI**: No Gradio, Streamlit, or custom React chat interface is provided. The platform exposes programmatic APIs for embedding into existing client applications.

- **Model training or fine-tuning pipelines**: The build integrates pre-trained foundation models (OpenAI, Anthropic). LoRA, RLHF, DPO, and domain-specific fine-tuning pipelines are out of scope.

- **Custom foundation model development**: No pretraining, continued pretraining, or architecture research. The build is a consumer of third-party model APIs.

- **Voice/audio processing pipelines**: No speech-to-text, text-to-speech, or real-time voice agent capabilities (e.g., no Twilio Voice integration, no Whisper fine-tuning).

- **Computer vision and multimodal vision pipelines**: No image generation, OCR, object detection, or visual reasoning agents. The platform handles text-based and structured-data reasoning only.

- **Video processing**: No video understanding, generation, or streaming analysis.

- **Robotics or IoT integration**: No ROS, MQTT, edge device orchestration, or sensor-fusion work.

- **Browser automation at scale**: No persistent browser agents, headless fleet management, or CAPTCHA solving infrastructure.

- **Blockchain or Web3 components**: No smart contracts, on-chain agents, crypto wallet integration, or decentralized identity.

- **HIPAA-grade healthcare compliance**: The build provides audit logging and access controls but is not validated against HIPAA, HITRUST, or equivalent healthcare-specific frameworks.

- **FedRAMP / IL5 government cloud certification**: The architecture is cloud-portable but is not pre-authorized at any US government FedRAMP baseline.

- **PCI-DSS payment processing**: No cardholder data handling, tokenization, or payment processing integration.

- **Automated red-team adversarial testing suites**: Out of scope for this build; safety testing is manual and advisory.

### 1.2 Infrastructure Not Provided

- **Production cloud provisioning (Terraform/CloudFormation)**: Reference deployment configs may exist, but full production-grade IaC for a specific cloud account is out of scope.

- **24/7 on-call rotation and incident response**: The build is delivered; ongoing SRE operations, paging, and incident management require a separate engagement.

- **Multi-region active-active deployment**: Single-region high-availability deployment is the documented target. Multi-region failover, traffic shifting, and disaster recovery across geographies are not included.

- **Cost optimization consulting**: No FinOps dashboards, reserved-instance planning, or per-workload cost attribution.

- **Legacy system migration**: No data migration from proprietary legacy systems, ETL reverse-engineering, or cutover planning.

---

## 2. Integration Boundaries

The following integrations are acknowledged as valuable but explicitly deferred:

- **Salesforce, SAP, Workday, ServiceNow connectors**: Generic REST/GraphQL adapters exist, but pre-built certified connectors for these enterprise suites require partner agreements and are out of scope.

- **Slack/Teams/Microsoft 365 native bots**: Webhook receivers may be documented as patterns, but fully featured, app-store-published bots are not delivered.

- **SSO providers beyond OIDC/OAuth2 generic flows**: Okta-specific, Azure-AD-specific, or Ping-specific deep integrations are out of scope; the build uses generic OIDC.

- **On-premise Active Directory / LDAP**: Federation to legacy on-prem identity providers is not provided.

---

## 3. Explicit Non-Goals

The build deliberately does **not** attempt to:

- **Replace human judgment in any domain**: It augments decision-making through Human-in-the-Loop Decision Support but does not substitute for licensed professionals (medical, legal, financial advice cannot be sourced from this system without qualified human review).

- **Guarantee model accuracy or hallucation freedom**: LLM outputs are probabilistic. The build provides confidence signals, retrieval grounding, and evaluation tooling, but cannot guarantee correctness.

- **Eliminate the need for prompt engineering**: Domain adaptation requires ongoing prompt tuning, evaluation, and refinement by humans.

- **Operate without human oversight**: Production deployment requires human-defined policies, approval gates, and intervention points.

---

## 4. Deferred Phases

The following are documented as future work and intentionally not part of this delivery:

- **Phase 7+**: Advanced agent capabilities including autonomous tool synthesis, self-modifying prompts, and cross-session memory consolidation beyond what's specified.
- **Customer-specific customizations**: Industry vertical templates (legal discovery, clinical summarization, financial due diligence) are out of scope unless separately scoped.

---

## 5. Reference: CONTEXT.md In-Scope Requirements (for clarity)

This out-of-scope document complements the in-scope requirements defined in CONTEXT.md:

| In-Scope Requirement | Status |
|----------------------|--------|
| Agent Orchestration (multi-agent, delegation, shared state) | In scope |
| Enterprise Workflow Automation (PostgreSQL, pgvector, APIs) | In scope |
| RAG & Knowledge Retrieval (vector search, semantic) | In scope |
| AI Memory & Persistence (PostgreSQL/pgvector) | In scope |
| Human-in-the-Loop Decision Support (approval gates) | In scope |
| AI Evaluation & Observability (decision paths, monitoring) | In scope |
| AI Governance & Security (audit log, access controls) | In scope |

Everything not listed in the table above, and not implemented as part of the in-scope deliverables, is considered out of scope per this document.
```

```file:README.md
# AI Systems Engineer — Agentic AI Build

## Deliverables Index

| Document | Purpose |
|----------|---------|
| CONTEXT.md | Functional and non-functional requirements |
| RESEARCH.md | Technology stack decisions and rationale |
| SPEC.md | Full proposal and engagement scope |
| OUT_OF_SCOPE.md | Explicit non-goals and out-of-scope items |
| PLAN-01 through PLAN-NN | Phased execution plans |

See `OUT_OF_SCOPE.md` for a precise enumeration of what is **not** included in this build.
```

```file:tests/test_out_of_scope_doc.py
"""Tests that verify OUT_OF_SCOPE.md exists and enumerates the required non-goals."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_OF_SCOPE = REPO_ROOT / "OUT_OF_SCOPE.md"


def test_out_of_scope_file_exists():
    """The OUT_OF_SCOPE.md document must exist at repository root."""
    assert OUT_OF_SCOPE.is_file(), f"Missing required file: {OUT_OF_SCOPE}"


def test_out_of_scope_has_required_sections():
    """OUT_OF_SCOPE.md must include the canonical non-goal sections."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")

    required_phrases = [
        "# OUT OF SCOPE",
        "## 1. Out-of-Scope Workstreams",
        "## 2. Integration Boundaries",
        "## 3. Explicit Non-Goals",
        "## 4. Deferred Phases",
        "Multi-tenant SaaS layer",
        "Mobile or desktop client applications",
        "Model training or fine-tuning pipelines",
        "Human-in-the-Loop Decision Support",
        "AI Governance & Security",
    ]

    for phrase in required_phrases:
        assert phrase in content, f"OUT_OF_SCOPE.md missing required phrase: {phrase!r}"


def test_out_of_scope_references_in_scope_requirements():
    """The document must list every CONTEXT.md in-scope functional requirement."""
    content = OUT_OF_SCOPE.read_text(encoding="utf-8")

    in_scope_keywords = [
        "Agent Orchestration",
        "Enterprise Workflow Automation",
        "RAG & Knowledge Retrieval",
        "AI Memory & Persistence",
        "Human-in-the-Loop Decision Support",
        "AI Evaluation & Observability",
        "AI Governance & Security",
    ]

    for keyword in in_scope_keywords:
        assert keyword in content, (
            f"OUT_OF_SCOPE.md must reference in-scope requirement: {keyword!r}"
        )


def test_readme_links_to_out_of_scope():
    """README.md must reference OUT_OF_SCOPE.md for discoverability."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "OUT_OF_SCOPE.md" in readme, "README.md must link to OUT_OF_SCOPE.md"
```

## Done When
- `OUT_OF_SCOPE.md` exists at the repository root and contains all six canonical sections (Out-of-Scope Workstreams, Integration Boundaries, Explicit Non-Goals, Deferred Phases, Reference table, headings).
- `README.md` exists at the repository root and references `OUT_OF_SCOPE.md` so reviewers can discover it.
- `tests/test_out_of_scope_doc.py` exists and `pytest tests/test_out_of_scope_doc.py` passes all 4 checks: file existence, required section phrasing, in-scope requirement coverage, and README linkage.
- The document explicitly enumerates at least the 13 non-implemented workstreams listed (multi-tenant SaaS, mobile clients, end-user chat UI, fine-tuning, voice, vision, video, robotics, browser automation at scale, blockchain, HIPAA, FedRAMP, PCI-DSS).
- Every CONTEXT.md functional requirement keyword (Agent Orchestration, Enterprise Workflow Automation, RAG & Knowledge Retrieval, AI Memory & Persistence, Human-in-the-Loop Decision Support, AI Evaluation & Observability, AI Governance & Security) appears in the in-scope reference table inside `OUT_OF_SCOPE.md`.

## Acceptance Notes
- This phase supports the overall project by establishing explicit non-goals before implementation work in subsequent phases begins, preventing reviewers from inferring that deferred features were simply forgotten.
- It addresses CONTEXT.md non-functional requirement framing ("Systems must support production-scale workloads; vector search queries must return results in <100ms…") by deferring multi-region and FinOps concerns and making the latency target boundary explicit.
- It complements — but does not duplicate — the in-scope language from SPEC.md (`Agent Orchestration` and the other six functional requirements) by giving each a "In scope" tick mark in the closing reference table.
- The deliverable is purely documentary and produces no executable code, but the `pytest` test suite makes the scope contract mechanically enforceable for CI, so a future contributor cannot silently delete a non-goal without breaking tests.
# OUT OF SCOPE

This document explicitly enumerates what is **not** included in this
build. Setting clear boundaries prevents scope creep, protects client
expectations, and helps reviewers evaluate what was actually delivered
against what was deliberately deferred.

> Read this together with [`README.md`](./README.md) (the seven pillars
> that *are* in scope) and [`docs/PROJECT_OVERVIEW.md`](./docs/PROJECT_OVERVIEW.md)
> (success criteria and stakeholder model).

---

## 1. Out-of-Scope Workstreams

### 1.1 Not Implemented in This Build

The following workstreams are out of scope for the current engagement
and would require separate work agreements. This is the canonical list
of deferred items; later phases of the engagement may pick any of these
up under their own change orders.

- **Multi-tenant SaaS layer**: No tenant isolation, per-tenant encryption
  keys, or billing/metering systems. The build assumes a single
  organizational tenant with internal access controls only.

- **Mobile or desktop client applications**: This build is a server-side
  platform with HTTP/WebSocket APIs only. No React Native, Swift, Kotlin,
  Electron, or PWA client work.

- **End-user-facing chat UI**: No Gradio, Streamlit, or custom React
  chat interface is provided. The platform exposes programmatic APIs
  for embedding into existing client applications.

- **Model training or fine-tuning pipelines**: The build integrates
  pre-trained foundation models (OpenAI, Anthropic). LoRA, RLHF, DPO,
  and domain-specific fine-tuning pipelines are out of scope.

- **Custom foundation model development**: No pretraining, continued
  pretraining, or architecture research. The build is a consumer of
  third-party model APIs.

- **Voice/audio processing pipelines**: No speech-to-text, text-to-speech,
  or real-time voice agent capabilities (e.g., no Twilio Voice
  integration, no Whisper fine-tuning, no voice agent loop).

- **Computer vision and multimodal vision pipelines**: No image
  generation, OCR, object detection, or visual reasoning agents. The
  platform handles text-based and structured-data reasoning only.

- **Video processing**: No video understanding, video generation, or
  streaming video analysis pipelines.

- **Robotics or IoT integration**: No ROS, MQTT, edge-device
  orchestration, or sensor-fusion work. No autonomous-vehicle, drone,
  or warehouse-robot integrations.

- **Browser automation at scale**: No persistent browser agents,
  headless fleet management, anti-bot evasion, CAPTCHA solving, or
  web-scraping infrastructure.

- **Blockchain or Web3 components**: No smart contracts, on-chain agents,
  crypto wallet integration, decentralized identity, or NFT/DeFi
  features.

- **HIPAA-grade healthcare compliance**: The build provides audit logging
  and access controls but is **not** validated against HIPAA, HITRUST,
  or equivalent healthcare-specific frameworks. PHI handling is not
  in scope.

- **FedRAMP / IL5 government cloud certification**: The architecture is
  cloud-portable but is **not** pre-authorized at any US government
  FedRAMP baseline (Low, Moderate, High) or DoD IL4/IL5.

- **PCI-DSS payment processing**: No cardholder data handling,
  tokenization, PAN storage, or payment-processing integration.

- **Automated red-team adversarial testing suites**: Out of scope for
  this build; safety testing is manual and advisory.

- **Customer-specific vertical templates**: Out of scope unless separately
  scoped under a change order (e.g., legal-discovery, clinical-summarization,
  financial-due-diligence templates).

### 1.2 Infrastructure Not Provided

- **Production cloud provisioning (Terraform / CloudFormation)**:
  Reference deployment configs may exist, but full production-grade
  IaC for a specific cloud account is out of scope.

- **24/7 on-call rotation and incident response**: The build is delivered;
  ongoing SRE operations, paging, and incident management require a
  separate engagement.

- **Multi-region active-active deployment**: Single-region
  high-availability deployment is the documented target. Multi-region
  failover, traffic shifting, and disaster-recovery across geographies
  are not included.

- **Cost-optimization / FinOps**: No FinOps dashboards, reserved-instance
  planning, or per-workload cost attribution.

- **Legacy system migration / data backfill**: No data migration from
  proprietary legacy systems, ETL reverse-engineering, or cutover
  planning.

- **Long-term operational support**: No SLA-backed operational support
  (L1/L2/L3) is included in this engagement.

---

## 2. Integration Boundaries

The following integrations are acknowledged as valuable but explicitly
deferred. Each is a candidate for a follow-on engagement.

- **Salesforce, SAP, Workday, ServiceNow certified connectors**:
  Generic REST/GraphQL adapter patterns exist, but pre-built certified
  connectors for these enterprise suites require partner agreements
  and are out of scope.

- **Slack / Teams / Microsoft 365 native bots**: Webhook receivers may
  be documented as patterns, but fully featured, app-store-published
  bots are not delivered.

- **SSO providers beyond OIDC/OAuth2 generic flows**: Okta-specific,
  Azure-AD-specific, Google Workspace-specific, or Ping-specific deep
  integrations are out of scope; the build uses generic OIDC.

- **On-premise Active Directory / LDAP**: Federation to legacy on-prem
  identity providers is not provided.

- **Legacy EDI / X12 / SWIFT integrations**: No financial messaging
  hubs or healthcare EDI pipelines are included.

- **Native CRM / ERP / ITSM data sync**: Direct bi-directional sync
  with external systems of record is delegated to customer-side
  integrations; the platform exposes REST/GraphQL but does not
  pre-build CRM integrations.

---

## 3. Explicit Non-Goals

The build deliberately does **not** attempt to:

- **Replace human judgment in any domain.** The platform augments
  decision-making through Human-in-the-Loop Decision Support but does
  not substitute for licensed professionals. Medical, legal, or
  financial advice cannot be sourced from this system without qualified
  human review.

- **Guarantee model accuracy or hallucation freedom.** LLM outputs are
  probabilistic. The build provides confidence signals, retrieval
  grounding, and evaluation tooling, but cannot guarantee correctness.

- **Eliminate the need for prompt engineering.** Domain adaptation
  requires ongoing prompt tuning, evaluation, and refinement by humans.

- **Operate without human oversight.** Production deployment requires
  human-defined policies, approval gates, and intervention points; the
  system is designed for *assisted* autonomy, not *unattended* autonomy.

- **Replace every workflow in an organization.** The platform is
  built to orchestrate a focused set of multi-agent workflows with
  the seven pillars; general-purpose task automation remains the
  customer's responsibility.

- **Provide offline / on-device operation.** Inference is performed
  against cloud-hosted foundation models. Local quantized inference is
  out of scope.

- **Be a low-code / no-code tool.** Workflows are configured in code
  (Python / LangGraph), not via a visual designer.

---

## 4. Deferred Phases

The following are documented as future work and intentionally not part
of this delivery:

- **Phase 7+ — Advanced agent capabilities.** Autonomous tool synthesis,
  self-modifying prompts, autonomous prompt-tuning loops, and
  cross-session memory consolidation beyond the scope of this engagement.
- **Phase 8+ — Customer-specific vertical templates.** Industry vertical
  templates (legal discovery, clinical summarization, financial due
  diligence, customer-support triage) are out of scope unless separately
  scoped.
- **Phase 9+ — Multi-tenant / SaaS hosting layer.** Per-tenant isolation,
  per-tenant key encryption, billing, metering, and tenant-facing
  admin UI.
- **Phase 10+ — Industry-specific compliance certifications.** HIPAA,
  HITRUST, FedRAMP, PCI-DSS, SOC 2 Type II readiness audits.
- **Phase 11+ — Front-end clients.** Any web, mobile, or desktop
  product surface; the current build is server-side only.

---

## 5. Reference: CONTEXT.md In-Scope Requirements (for clarity)

This out-of-scope document complements the in-scope requirements
defined in `CONTEXT.md` and mapped in `README.md`. Every keyword below
appears verbatim in the in-scope section to give reviewers a single
place to confirm coverage.

| In-Scope Requirement                       | Status   |
|--------------------------------------------|----------|
| Agent Orchestration                        | In scope |
| Enterprise Workflow Automation             | In scope |
| RAG & Knowledge Retrieval                  | In scope |
| AI Memory & Persistence                    | In scope |
| Human-in-the-Loop Decision Support         | In scope |
| AI Evaluation & Observability              | In scope |
| AI Governance & Security                   | In scope |

Everything **not** listed in the table above, and **not** implemented
as part of the in-scope deliverables, is considered out of scope per
this document.

---

## 6. How to Use This Document

- **For reviewers**: before flagging a missing feature, check it
  against sections 1–5 above. If it is listed, it is intentionally
  out of scope for this engagement; it is not an oversight.
- **For the engagement owner**: when a stakeholder requests one of
  these items, point them at the corresponding entry here. Capture
  scope changes in writing via a change order before work begins.
- **For the engineering team**: a contributor proposing to add an
  out-of-scope item must first amend this document in the same PR
  that introduces the code (and remove the corresponding test in
  `tests/test_out_of_scope_doc.py`).

---

*Last updated: 2026-07-02. Maintained alongside `README.md`,
`docs/PROJECT_OVERVIEW.md`, and `tests/test_out_of_scope_doc.py`.*

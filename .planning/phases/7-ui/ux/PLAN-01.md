## Phase Goal
Define the UI/UX approach, layout patterns, and interaction models for the AI Systems Engineer platform's human-in-the-loop interfaces and operational dashboards.

## Files to Create

```file:docs/ui-ux/design-system.md
# Design System

## Visual Language

### Color Tokens
- `surface.base`: #0F1115 (deep slate — primary canvas)
- `surface.raised`: #1A1D24 (cards, modals)
- `surface.overlay`: rgba(15, 17, 21, 0.85) (backdrops)
- `border.subtle`: #262A33
- `border.strong`: #3A3F4B
- `text.primary`: #E8EAED
- `text.secondary`: #9AA0A6
- `text.muted`: #6B7280
- `accent.primary`: #4F8CFF (primary actions, focus states)
- `accent.success`: #34D399 (completed agent runs, healthy status)
- `accent.warning`: #FBBF24 (degraded performance, retry pending)
- `accent.danger`: #F87171 (failures, destructive actions)
- `accent.info`: #60A5FA (informational banners)

### Typography
- Font stack: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Monospace stack: `"JetBrains Mono", "Fira Code", monospace`
- Scale: 12 / 14 / 16 / 18 / 20 / 24 / 30 / 36 / 48 (rem-based, 16px base)

### Spacing Scale
4px base unit: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64

### Radius
- `radius.sm`: 4px (inputs, chips)
- `radius.md`: 8px (buttons, cards)
- `radius.lg`: 12px (modals, panels)
- `radius.full`: 9999px (avatars, status dots)

## Component Inventory

### Primitives
- Button (primary / secondary / ghost / danger; sizes sm/md/lg)
- Input (text, textarea, select, combobox)
- Card
- Modal / Drawer
- Tabs
- Toast / Banner
- Badge / Tag / Chip
- Tooltip / Popover
- Table (virtualized for large datasets — agent run history)
- Skeleton (loading states for agent traces)
- EmptyState

### Domain Components
- `<AgentRunTimeline>`: vertical timeline of agent steps with status, latency, tokens
- `<ApprovalGate>`: renders approval request with approve/reject/escalate actions
- `<TraceViewer>`: collapsible tree of agent decision paths with token counts
- `<KnowledgeChunkCard>`: retrieved RAG chunk with similarity score, source, snippet
- `<EvalResultPanel>`: per-test-case pass/fail with diff and rubric scores
- `<AuditLogRow>`: timestamped governance event with actor, action, target, hash
- `<McpServerStatus>`: connection indicator + tool list per MCP server

## Iconography
Lucide React — consistent stroke weight, tree-shakeable. Use for navigation, status, and action affordances.

## Motion
- Transitions: 150ms ease-out (micro), 250ms ease-in-out (panel)
- Skeleton shimmer for loading traces
- Reduce-motion preference honored via `prefers-reduced-motion`
```

```file:docs/ui-ux/information-architecture.md
# Information Architecture

## Top-Level Navigation

```
/                       Dashboard (overview, active runs, alerts)
/agents                 Agent registry (list, create, edit)
/agents/[id]            Agent detail (config, recent runs, eval scores)
/workflows              Workflow list
/workflows/[id]         Workflow editor + execution history
/runs                   Run history (cross-agent, filterable)
/runs/[id]              Run detail (timeline, traces, artifacts)
/knowledge              Knowledge bases (RAG sources)
/knowledge/[id]         KB detail (documents, chunks, retrieval test)
/approvals              Pending human-in-the-loop approvals queue
/evaluations            Eval suites + results
/observability          Dashboards (latency, cost, error rates)
/governance             Audit log, access policies, retention rules
/settings               Workspace, integrations (MCP servers), API keys
```

## Primary Layout

```
┌─────────────────────────────────────────────────────────────┐
│ TopBar: workspace switcher · global search · user menu     │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  Side    │  Page content                                    │
│  Nav     │  (breadcrumbs · page header · body)              │
│  (icons  │                                                  │
│  + label)│                                                  │
│          │                                                  │
├──────────┴──────────────────────────────────────────────────┤
│ StatusBar: env · MCP health · active runs count · version  │
└─────────────────────────────────────────────────────────────┘
```

- Side nav collapsible to icon-only at <1280px viewport width.
- StatusBar always visible — surfaces operational health for engineers.

## Page Patterns

### Dashboard
- 3-column responsive grid (collapses to 1 on <768px)
- Cards: Active Runs (live tail), Recent Approvals, Cost This Week, Eval Pass Rate, Top Errors
- Each card links to its detail view

### Run Detail
- 3-pane layout:
  - Left (320px): step list / timeline
  - Center (flex): current step detail — prompt, response, tool calls
  - Right (360px): metadata — agent, tokens, cost, latency, approval gates
- Sticky "Pause / Resume / Cancel" action bar at top

### Workflow Editor
- Node-based canvas (React Flow)
- Left palette: agent nodes, tool nodes, condition nodes, human-approval nodes
- Right inspector: selected node configuration
- Bottom drawer: validation errors and dry-run results

### Approval Queue
- Table with columns: Requested at · Workflow · Step · Summary · Action buttons
- Inline approve/reject; rejection opens reason modal
- Bulk actions for grouped approvals

## Empty States
Every list view defines an empty state with:
- Illustrative icon
- One-sentence explanation of what this view shows
- Primary CTA (e.g., "Create your first agent")

## Error States
- Inline form errors: red border + helper text directly under field
- Page-level errors: full-bleed card with error code, message, and "Retry" / "Contact support" actions
- Streaming interruptions (agent runs): reconnecting banner with last-known-good timestamp
```

```file:docs/ui-ux/ux-patterns.md
# UX Patterns

## Human-in-the-Loop Approval Gates

### When to Surface
Triggered automatically when a workflow node is configured with `requires_approval: true` or when an agent invokes a tool classified as sensitive (file deletion, external message send, payment-related).

### Presentation
1. Toast notification: "Approval requested: Send 12 invoices via Stripe"
2. Click → opens modal with full context:
   - What will happen (plain-English summary generated by agent)
   - Inputs / parameters (collapsible JSON viewer)
   - Reversibility indicator (green = reversible, red = one-way)
   - Confidence score from agent
3. Actions: Approve · Reject (with reason) · Request more info (sends prompt back to agent)
4. Audit row written regardless of choice

### SLA
- Show "Waiting X minutes" indicator
- Highlight in red at 30 minutes idle
- Escalation rules configurable per workflow (notify secondary approver after threshold)

## Agent Trace Exploration

### Collapsible Decision Tree
Each agent run produces a tree of decisions. Default expansion:
- Root fully expanded
- Children collapsed beyond depth 3
- User can pin / unpin branches for comparison

### Token & Cost Annotations
- Each node shows `↑ 1.2k tokens · $0.018 · 1.4s`
- Hover for breakdown by prompt vs. completion
- Aggregate shown in run header

### Diff Between Runs
- "Compare with previous run" toggle
- Highlights diverged nodes side-by-side

## RAG Retrieval Feedback

### Inline Relevance Voting
Each retrieved chunk card has thumbs-up / thumbs-down. Vote writes back to eval dataset and improves future retrievals via feedback signal in metadata.

### "Why this chunk?" Tooltip
Shows the embedding distance, matched query terms, and reranker score — helps engineers debug retrieval quality.

## Eval Suite Authoring

### Test Case Editor
- Input column + expected output column
- Optional rubric (free-text criteria scored by LLM judge)
- "Run on this case" button for quick iteration
- Bulk import from JSONL

### Result Review
- Per-case pass/fail with side-by-side actual vs expected
- For rubric-based: score 1-5 with judge's reasoning
- Filter by failure mode tags

## Observability Dashboards

### Default Widgets
- p50 / p95 / p99 latency per agent (line chart)
- Token spend per day, stacked by model (area chart)
- Error rate by error code (bar chart)
- Approval queue depth over time (sparkline)

### Time Range Selector
- Preset: 1h, 6h, 24h, 7d, 30d
- Custom range with timezone-aware picker
- Default: last 24h

### Drilldown
- Click any chart segment → filtered run list

## Governance & Audit

### Audit Log Search
- Faceted search: actor, action type, target resource, date range
- Each row expandable to show full payload
- "Export to CSV" for compliance reporting

### Access Policy Editor
- Roles: Admin, Engineer, Reviewer, Viewer
- Resource-level permissions (per agent, per workflow, per KB)
- Preview pane shows effective permissions for selected principal

## Keyboard Shortcuts (Power User)
- `g a` → go to Agents
- `g r` → go to Runs
- `g p` → go to Approvals
- `c` → create (context-sensitive)
- `/` → focus search
- `?` → shortcut cheat sheet
- `Esc` → close modal/drawer

## Accessibility
- WCAG 2.1 AA target
- All interactive elements keyboard-reachable
- Focus rings visible (never `outline: none` without replacement)
- ARIA labels on icon-only buttons
- Color contrast ≥4.5:1 for body text
- Screen reader announcements for live agent status changes (`aria-live="polite"`)
```

```file:docs/ui-ux/wireframes/dashboard.md
# Dashboard Wireframe

## Desktop (≥1280px)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ☰  Acme AI Workspace        🔍 Search...            🔔 3   👤 jdoe  │
├──────────┬───────────────────────────────────────────────────────────┤
│ ⌂ Home   │  Dashboard                              Last 24h ▾        │
│ 🤖 Agents│  ┌─────────────────┬─────────────────┬─────────────────┐  │
│ 🔀 Flows │  │ Active Runs     │ Pending Approv. │ Cost This Week  │  │
│ 📜 Runs  │  │      12         │       3         │    $42.18       │  │
│ 📚 KB    │  │  ↑ 4 from yest. │  ⚠ 1 > 30 min   │  ↓ 8% vs prior  │  │
│ ✋ Apprv │  └─────────────────┴─────────────────┴─────────────────┘  │
│ ✅ Evals │  ┌─────────────────────────┬────────────────────────────┐ │
│ 📊 Obs   │  │ Eval Pass Rate          │ Top Errors                 │ │
│ 🛡 Gov   │  │   ╭───────╮             │ 1. timeout_stripe (14)      │ │
│ ⚙ Set   │  │   │ 87.3% │             │ 2. rate_limit_openai (9)    │ │
│          │  │   ╰───────╯             │ 3. invalid_json (6)         │ │
│          │  │  Target: 90%            │ [View all →]               │ │
│          │  └─────────────────────────┴────────────────────────────┘ │
│          │  ┌──────────────────────────────────────────────────────┐ │
│          │  │ Recent Runs                                         │ │
│          │  │ ✓ inv-proc-001  · 2.3s  · $0.04  · 2 min ago       │ │
│          │  │ ⏳ rag-query-88  · running · 12s · $0.11 · now      │ │
│          │  │ ✗ kb-sync-22    · failed · 4 min ago                │ │
│          │  └──────────────────────────────────────────────────────┘ │
├──────────┴───────────────────────────────────────────────────────────┤
│ 🟢 prod  ·  3 MCP servers connected  ·  12 active  ·  v0.7.2       │
└──────────────────────────────────────────────────────────────────────┘
```

## Mobile (<768px)
- Cards stack vertically (1 column)
- Side nav becomes hamburger drawer
- StatusBar moves to top, collapses to icons only
```

```file:docs/ui-ux/wireframes/run-detail.md
# Run Detail Wireframe

```
┌──────────────────────────────────────────────────────────────────────┐
│ ← Runs / inv-proc-3401                              [Pause][Cancel] │
├──────────┬──────────────────────────────────────┬────────────────────┤
│ Steps    │  Step 4 of 7: extract_invoice_data  │ Metadata           │
│          │                                      │                    │
│ ✓ 1 load │  ┌────────────────────────────────┐  │ Agent:             │
│ ✓ 2 val  │  │ Prompt                        │  │  invoice-extractor │
│ ✓ 3 fet  │  │ Extract line items from...     │  │                    │
│ ● 4 ext  │  │                                │  │ Status: running    │
│ ○ 5 rag  │  │ Response                       │  │ Started: 14:02:11  │
│ ○ 6 sum  │  │ {                              │  │ Duration: 12.4s    │
│ ○ 7 out  │  │  "vendor": "Acme Corp",        │  │                    │
│          │  │  "total": 1240.00,             │  │ Tokens:            │
│          │  │  "items": [...]                │  │  ↑ 1.2k  ↓ 380     │
│          │  │ }                              │  │                    │
│          │  │ Tool Calls (2)                 │  │ Cost: $0.018       │
│          │  │ ▸ pgvector.search (142ms)      │  │                    │
│          │  │ ▸ json_parser (3ms)            │  │ Confidence: 0.94   │
│          │  └────────────────────────────────┘  │                    │
│          │                                      │ Approval:          │
│          │  [Retry step] [View raw trace]       │  Not required      │
└──────────┴──────────────────────────────────────┴────────────────────┘
```

### Interactions
- Click any prior step in left rail → loads that step in center pane
- Right pane remains visible on ≥1280px; collapses to drawer trigger on smaller screens
- "Retry step" forks the run from that node (creates new run id)
- "View raw trace" opens full decision tree in modal
```

```file:docs/ui-ux/wireframes/approval-modal.md
# Approval Modal Wireframe

```
┌──────────────────────────────────────────────────────────────┐
│  Approval Requested                                    [✕]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Workflow: invoice-processing                                │
│  Step: send_payment_batch                                    │
│  Requested by: agent · payment-orchestrator                  │
│  Waiting: 4 minutes                                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ What will happen                                       │  │
│  │ Send 12 invoices totaling $14,230.00 via Stripe to    │  │
│  │ the vendor list returned by step 5. Each invoice is   │  │
│  │ for the current billing period.                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Reversibility: ⚠ One-way action (external payment)         │
│  Agent confidence: 94%                                        │
│                                                              │
│  ▸ View parameters (JSON)                                    │
│  ▸ View prior step outputs                                   │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  [Reject...] [Request info]            [Approve]             │
└──────────────────────────────────────────────────────────────┘
```

### Reject Flow
Reject button opens reason modal:
- Quick reasons (chips): "Wrong recipient", "Amount incorrect", "Duplicate", "Other"
- Free-text area (required when "Other" chosen)
- Submit → writes audit row with reason, notifies agent, terminates run
```

```file:docs/ui-ux/component-specs/AgentRunTimeline.md
# Component Spec: `<AgentRunTimeline>`

## Purpose
Vertical timeline of agent execution steps with status, latency, and token usage.

## Props
```ts
interface AgentRunTimelineProps {
  steps: AgentStep[];
  activeStepId?: string;
  onStepSelect?: (stepId: string) => void;
}
```

## Visual States
| State | Icon | Border | Background |
|-------|------|--------|------------|
| pending | ○ | `border.subtle` | transparent |
| running | ◌ (spinner) | `accent.primary` | `accent.primary` @ 8% |
| success | ✓ | `accent.success` | `accent.success` @ 8% |
| failed | ✗ | `accent.danger` | `accent.danger` @ 8% |
| skipped | — | `border.subtle` | `surface.raised` |

## Layout
- 32px left rail with status icon
- Step name + relative timestamp (`2 min ago`)
- Expand chevron on right
- Expanded body: token count, cost, duration, error message if failed

## Behavior
- Click row → emits `onStepSelect`
- Active step has `accent.primary` left border (2px)
- Failed steps auto-expand on first render
- Virtualized when step count > 100
```

```file:docs/ui-ux/component-specs/ApprovalGate.md
# Component Spec: `<ApprovalGate>`

## Purpose
Renders an approval request with context, parameters, and approve/reject actions.

## Props
```ts
interface ApprovalGateProps {
  request: ApprovalRequest;
  onApprove: () => Promise<void>;
  onReject: (reason: string, category?: RejectionCategory) => Promise<void>;
  onRequestInfo: (question: string) => Promise<void>;
  disabled?: boolean;
}
```

## Composition
- Header: workflow name, step name, waiting duration
- Summary card: plain-English description (from agent)
- Reversibility badge + confidence score
- Collapsible JSON parameter viewer
- Action footer: Reject / Request info / Approve (Approve is primary)

## Loading & Error States
- Buttons disable and show spinner during async actions
- On error: inline error banner above action footer with retry option
- Optimistic UI not used for approvals — always wait for server confirmation (audit integrity)

## Accessibility
- Modal traps focus
- `role="alertdialog"` with `aria-labelledby` pointing to header
- Action buttons labeled verb + object ("Approve payment batch", not just "Approve")
- `aria-live="polite"` region for status updates after action
```

```file:docs/ui-ux/component-specs/TraceViewer.md
# Component Spec: `<TraceViewer>`

## Purpose
Tree view of agent decision paths with token annotations and branch comparison.

## Props
```ts
interface TraceViewerProps {
  trace: TraceNode;
  highlightDiffWith?: string; // runId to compare against
  onNodePin?: (nodeId: string) => void;
  pinnedNodes?: string[];
}
```

## Tree Node
```
▾ llm_call (gpt-4o)
    ↑ 1.2k ↓ 380 · $0.018 · 1.4s
    ▸ tool: pgvector.search  (returned 4 chunks)
    ▸ tool: json_parser       (ok)
    ▸ decision: continue
```

## Interactions
- Click node → opens detail panel with full prompt/response
- Right-click → context menu (pin, copy as JSON, mark as eval fixture)
- Hover → shows token breakdown popover
- Compare mode: divergent nodes get amber border + side-by-side panel

## Performance
- Virtualized rendering beyond 200 nodes
- Lazy expansion (children loaded on click)
- Token formatting: `1.2k`, `24.1k`, etc.
```

```file:docs/ui-ux/component-specs/KnowledgeChunkCard.md
# Component Spec: `<KnowledgeChunkCard>`

## Purpose
Display a retrieved RAG chunk with relevance metadata and inline feedback controls.

## Props
```ts
interface KnowledgeChunkCardProps {
  chunk: RetrievedChunk;
  onVote?: (vote: 'up' | 'down') => void;
  onViewSource?: () => void;
}
```

## Layout
```
┌────────────────────────────────────────────────────────┐
│ 📄 vendor-agreements.pdf · p.4          sim: 0.87  ⓘ  │
│ "Payment terms are net-30 from invoice date. Late     │
│  payments accrue 1.5% monthly interest..."             │
│                                                        │
│ 👎 👍                          [View source document]  │
└────────────────────────────────────────────────────────┘
```

## States
- Default: `surface.raised` background
- Hovered: `border.strong` + shadow
- Voted (up): `accent.success` left border
- Voted (down): `accent.warning` left border
- Low similarity (<0.5): dimmed opacity, warning tooltip

## Information Density
- Compact mode (table cell): just snippet + score, 2 lines max
- Full mode (panel): chunk text up to 200 chars + "show more"
```

```file:docs/ui-ux/component-specs/EvalResultPanel.md
# Component Spec: `<EvalResultPanel>`

## Purpose
Display eval suite results with pass/fail status and per-case detail.

## Props
```ts
interface EvalResultPanelProps {
  suiteId: string;
  results: EvalCaseResult[];
  onRerun?: (caseIds: string[]) => void;
}
```

## Layout
```
┌────────────────────────────────────────────────────────┐
│ Suite: invoice-extraction-v3    Pass: 87/100  87% ▴ 2 │
├────────────────────────────────────────────────────────┤
│ ☐ ✓ case_001  total_amount    expected: 1240.00        │
│ ☐ ✓ case_002  vendor_name     expected: "Acme Corp"    │
│ ☐ ✗ case_003  line_items      expected: [...]          │
│   ↳ diff: missing "tax" field                          │
│ ☐ ⚠ case_
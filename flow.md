# MataQorLab — Refactor Existing Data Pipeline into AI-Orchestrated Conversational Workflow

> **Final status: DEVELOPMENT SCOPE CLOSED — 20 Aug 2026**
>
> The AI-orchestrated workflow described in this document is implemented. The
> model understands, plans, asks, selects typed tools and explains; server-owned
> WorkflowEngine/analytics code remains authoritative for state transitions and
> deterministic computation. Interim `STOP`, `INTERNAL ONLY` and pending-smoke
> notes below are retained as historical phase records and are superseded by the
> final closure decision and end-of-file marker in this document. Live staging and production
> rollout checks are release gates, not unfinished implementation in this flow.
>
> **สถานะสุดท้าย: ปิดขอบเขตงานพัฒนาแล้ว — 20 ส.ค. 2026**
>
> Workflow แบบ AI Agent ตามเอกสารนี้พัฒนาเสร็จแล้ว: AI ทำหน้าที่เข้าใจ วางแผน
> ถาม เลือก Typed Tool และอธิบายผล ส่วน WorkflowEngine/Analytics ฝั่ง Server
> เป็นผู้มีอำนาจตัดสิน state และคำนวณแบบ deterministic ข้อความ `STOP`,
> `INTERNAL ONLY` และ pending smoke ใน Phase เก่าด้านล่างเป็นประวัติ และให้ถือ
> Final Closure และ Marker ท้ายไฟล์เป็นสถานะล่าสุด การทดสอบ Live
> Staging/Production ถูกย้ายไปเป็น Release Gate ไม่ใช่งาน implementation ที่ค้าง
> ใน Flow นี้

You are working on an existing project called **MataQorLab**.

MataQorLab is a governed data-analysis SaaS. It supports data from uploaded files, REST APIs, and databases, then prepares, cleans, maps, validates, analyzes, calculates KPIs/findings, and generates business insights/reports.

Current stack:

* Frontend: Next.js
* Backend: FastAPI / Python
* Analysis: DuckDB + pandas
* Database: Supabase Postgres
* Raw file storage: Supabase Storage
* Redis / worker architecture may be used for long-running jobs
* Existing modules already include:

  * ingestion
  * ETL / data preparation
  * cleaning
  * cleaning profiles
  * mapping
  * validation
  * data-quality reporting
  * analytics
  * KPI calculation
  * Data Contract
  * computation/data-readiness/business-context assurance

## Main Objective

Refactor the current workflow from a monolithic pipeline such as:

```text
Upload/API/Database
→ ETL
→ Cleaning
→ Mapping
→ Validation
→ Analysis
```

where the backend runs many operations in one execution, into an **AI-orchestrated conversational workflow**.

The new behavior should be:

```text
User attaches File / API / Database
        ↓
Source is stored safely
        ↓
Lightweight source inspection
        ↓
AI reads source profile + workflow state
        ↓
AI decides the smallest necessary next step
        ↓
AI may ask the user a context-specific question
        ↓
Backend executes ONE deterministic tool
        ↓
Tool result is persisted
        ↓
AI reads the structured result
        ↓
AI decides the next step
        ↓
Repeat until READY_FOR_ANALYSIS
```

The AI must behave as an **orchestrator**, not as the system performing deterministic data operations.

---

# Core Design Principle

The LLM must only:

```text
Understand
→ Decide
→ Ask
→ Request Tool
→ Explain
```

The backend must continue performing:

```text
ETL / Prepare
Cleaning
Mapping
Validation
Calculation
Statistics
Analytics
```

using deterministic Python / DuckDB / pandas logic.

Do not move data-processing logic into the LLM.

Do not ask the LLM to calculate KPIs directly.

Do not let the LLM modify datasets directly.

---

# Important Requirement

Do NOT rewrite the whole existing data platform.

First inspect the current project architecture and existing ETL, cleaning, mapping, validation, analytics, database models, chat flow, and worker/job system.

Reuse existing implementation wherever possible.

The goal is mainly to:

1. separate the existing monolithic pipeline into independently executable steps;
2. persist workflow state;
3. expose those steps as controlled internal tools;
4. introduce an AI orchestrator above them;
5. allow the workflow to pause for user decisions;
6. resume from the correct state after the user responds;
7. avoid rerunning completed steps unnecessarily.

Before changing code, identify the current components that can be reused.

---

# Bridge — Current System to Target Architecture

This section maps the **existing MataQorLab codebase** to the target design in this document.
Use it during Phase 1 assessment and every subsequent refactor phase.
Do not treat the target tables/modules below as a greenfield rewrite.

## Current State Mapping

| Target concept (this doc) | Existing module / artifact | Reuse strategy |
|---|---|---|
| `inspect_source()` | `data_setup.build_scan_result()`, `column_profile.build_column_profile()`, `chat/ingest.py` source loading | **Wrap as-is** — scan is already lightweight and non-destructive |
| `prepare_data()` | `data_cleaning.prepare_handle_for_analysis()`, `dataset_engine.DatasetHandle.prepare_for_analysis()`, structural normalization inside `data_setup.load_setup_handle()` | **Wrap/refactor** — extract a single bounded prepare entrypoint from existing helpers |
| `clean_data()` | `data_cleaning.clean_dataframe()`, `clean_handle_duckdb()`, `etl_pipeline.apply_recipe_dataframe()`, `apply_recipe_duckdb()` | **Wrap as-is** — profiles already exist (`standard`, `financial`, `conservative`, `aggressive`) |
| `map_schema()` | `domain_analytics.infer_semantic_roles()`, `DataSetupCopilot` mapping UI, `column_mappings_memory` / governed mapping memory | **Wrap + extend** — add confidence policy and partial auto-map behavior |
| `validate_data()` | `etl_pipeline.validate_data_contract()`, `etl_pipeline.build_cleaning_preview()`, contract quality alerts | **Wrap as-is** |
| `analyze_data()` | `chat/ingest.py`, `analysis_agent.py`, `analytics_service.py`, `domain_analytics.compute_domain_kpis()` | **Reuse after readiness gate** — chat already runs analytics on approved datasets |
| Workflow persistence | `data_setup_sessions` table (`adaptive_data_setup_copilot.sql`) | **Evolve, do not duplicate** — extend session model before creating parallel `analysis_workflows` |
| Step history / artifacts | `data_setup_sessions.scan_result`, `answers`, `column_mapping`, `cleaning_recipe`, `business_context`, `preview_result`, `processing_progress` | **Map into `workflow_steps.output`** — same information, finer granularity over time |
| Data Contract | `etl_pipeline.normalize_data_contract()`, `validate_data_contract()`, `cleaning_recipe.data_contract`, `business_context` on session | **Evolve in place** — progressive collection already partially exists in wizard answers |
| Tool execution / ETL run | `data_setup.process_data_setup_session()`, `etl_execution.execute_etl_recipe()` | **Keep** — this is the deterministic execution path |
| Background jobs | `data_setup_worker.py`, `worker.py`, `claim_data_setup_sessions` RPC | **Reuse** — queue long-running tool steps through existing worker pattern |
| Dataset catalog / lineage | `dataset_catalog.register_completed_dataset_version()`, `dataset_versions`, `p1_unified_dataset_catalog.sql` | **Reuse as-is** |
| ETL recipes / runs | `etl_recipes`, `etl_pipeline_runs`, `etl_workflows.sql` | **Reuse as-is** — tool outputs should continue linking here |
| Assurance separation | `decision_assurance.py`, readiness checks in chat routes | **Preserve and surface in workflow UX** |
| Chat orchestration (today) | `chat/service.py`, `chat/context_builder.py`, `chat/stream_handler.py` | **Extend, not replace** — add orchestrator layer above chat completion |
| Data setup UI (today) | `DataSetupCopilot.tsx` embedded in `Chat.tsx` | **Migrate gradually to conversational cards** — see Migration Strategy |
| Onboarding lifecycle | `customer_experience.py` (`prepare_data`, `first_analysis` steps) | **Update step detection** once workflow states change |

### Proposed module map (reuse-first)

```text
services/tools/inspect_source.py      → wrap data_setup.build_scan_result + column_profile
services/tools/prepare_data.py        → wrap data_cleaning.prepare_handle_for_analysis
services/tools/clean_data.py          → wrap data_cleaning + etl_pipeline.apply_recipe_*
services/tools/map_schema.py          → wrap domain_analytics.infer_semantic_roles + session mapping
services/tools/validate_data.py       → wrap etl_pipeline.validate_data_contract
services/tools/analyze_data.py        → delegate to existing chat/analytics pipeline

services/workflow/state.py            → evolve from data_setup_sessions fields first
services/workflow/engine.py           → NEW — authorization/transition layer above handlers
services/orchestrator/*               → NEW — structured LLM decisions for chat turns
```

### Naming alignment (do not fork terminology)

| UX label in this doc | Existing code / DB value |
|---|---|
| Standard | `standard` |
| Financial | `financial` |
| Careful | `conservative` |
| Deep Clean | `aggressive` |

Always use code/DB identifiers in implementation.
Use UX labels only in user-facing copy.

### Database evolution strategy

**Default path: evolve `data_setup_sessions`, do not create a second workflow system yet.**

Phase 3 should prefer:

1. add nullable workflow-oriented fields to `data_setup_sessions` (`next_action`, richer `context`, per-step timestamps) **or**
2. add a child `workflow_steps` table keyed by `data_setup_session_id`

Only introduce separate `analysis_workflows` tables if Phase 1 proves the session model cannot express:

* independent step retry without rerunning the whole session
* stale/superseded downstream artifacts after contract changes
* orchestrator resume across unrelated chat turns

Existing session statuses already overlap with the target model:

```text
scanning / awaiting_answers / previewing / preview_ready
→ INSPECTED / AWAITING_USER

approved / processing
→ TOOL_RUNNING

ready
→ READY_FOR_ANALYSIS

failed / cancelled
→ FAILED / CANCELLED
```

Existing `current_step` values (`scan`, `structure`, `mapping`, `cleaning`, `business_context`, `review`, `processing`, `ready`) map directly to target workflow steps.

## Existing API Inventory

Inspect and extend these routes before adding new public endpoints.

### Data Setup (workflow precursor — keep compatible)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/data-setup/scan` | Create/resume session, run source scan (`build_scan_result`) |
| `GET` | `/data-setup/resume` | Resume in-progress session by source fingerprint |
| `GET` | `/data-setup/{session_id}` | Fetch session state |
| `PATCH` | `/data-setup/{session_id}` | Save draft answers/mapping/profile/context |
| `POST` | `/data-setup/{session_id}/preview` | Preview cleaning result without full materialization |
| `POST` | `/data-setup/{session_id}/approve` | Approve recipe and enqueue processing |
| `POST` | `/data-setup/{session_id}/cancel` | Cancel session |

Backend handlers live in `backend/app/api/routes.py`.
Core logic lives in `backend/app/services/data_setup.py`.

### Chat / Analysis (downstream — already gated on ready setup)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat` | Synchronous chat completion |
| `POST` | `/chat/stream` | Streaming chat completion |

Both routes call `_require_ready_data_setup()` when a file/connection is attached without an agent session.
Chat requests already accept `data_setup_session_id` and `dataset_version_id`.

### Related platform APIs (reuse, do not duplicate)

| Area | Examples |
|---|---|
| Files / upload | `POST /files/validate-upload`, `GET /files` |
| Dataset catalog | `GET /datasets`, `GET /datasets/{catalog_id}/versions`, `GET /dataset-versions/{id}/lineage` |
| Governance / memory | `GET/POST /governance/memories`, `GET /governance/context` |
| ETL schedules | existing ETL owner routes backed by `etl_recipes` / `etl_pipeline_runs` |

### Target API additions (later phases only)

Prefer internal orchestration first. Add only when the frontend needs them:

```text
POST /workflows/{id}/message     → optional; may remain internal to POST /chat
POST /sources/{id}/inspect       → optional; may remain internal to POST /data-setup/scan
```

**Rule:** `POST /chat` stays the primary user-facing interface.
Workflow complexity stays server-side.

## Migration Strategy

The current UX is a **wizard inside chat** (`DataSetupCopilot.tsx`), not yet a fully conversational orchestrator.
Migrate in place; do not delete the wizard until chat parity exists.

### Phase coexistence plan

| Phase | User experience | Backend |
|---|---|---|
| **Now → Phase 4** | Wizard remains primary for setup; chat blocked until session `ready` | Split monolithic `process_data_setup_session()` into callable tools; persist step-level state on session |
| **Phase 5–6** | Chat begins asking contextual questions for new uploads; wizard still available as fallback | Orchestrator returns `ask_user` / `tool_call`; workflow engine authorizes tools |
| **Phase 7–8** | Chat becomes primary setup path; wizard hidden behind feature flag or "Advanced setup" | Same APIs; `DataSetupCopilot` reads/writes session via orchestrator decisions |
| **Phase 9+** | Wizard deprecated after parity checklist passes | Remove wizard-only code paths |

### Parity checklist before wizard removal

1. File, API, and SQL sources all completable through chat alone
2. Every wizard step has an equivalent structured chat card or question
3. Failed step retry works without rerunning earlier steps
4. Session resume survives refresh and cross-device return
5. Approved dataset still publishes to `dataset_versions` with lineage intact
6. `_require_ready_data_setup()` continues to protect `/chat` and `/chat/stream`

### Compatibility rules during migration

* Keep `data_setup_session_id` on chat requests until frontend fully switches to workflow id (if ever renamed).
* Do not break `POST /data-setup/scan` response shape — mobile/clients may depend on it.
* Published `output_file` / `dataset_version_id` on session remain the chat attachment contract.

## MVP Scope

Implement the **smallest runnable vertical slice** before building the full AI orchestrator.
This reduces risk and keeps the app usable after every merge.

### MVP = Phase 1 through Phase 4 only

Deliver:

1. **Phase 1** — written assessment (no behavior change)
2. **Phase 2** — independent tool handlers wrapping existing logic
3. **Phase 3** — step-level persistence on/evolved from `data_setup_sessions`
4. **Phase 4** — workflow engine that validates tool calls, dependencies, retries, and stale marking

### Explicitly out of MVP

Do **not** start MVP work on:

* full LLM orchestrator (`services/orchestrator/*`)
* replacing `DataSetupCopilot` UI
* new public workflow REST surface beyond existing `/data-setup/*`
* analysis/KPI generation changes
* database/API/REST API source UX redesign (Steps 21–22)

### MVP done criteria

The MVP is complete when all of the following work **without** conversational AI driving the flow:

```text
Upload source
→ inspect_source (standalone)
→ prepare_data (standalone)
→ clean_data (standalone, can pause with awaiting_user status)
→ map_schema (standalone)
→ validate_data (standalone)
→ session marked ready
→ existing /chat analytics path unchanged
```

Add a thin internal test harness or admin-only endpoint to invoke each tool by name.
The wizard may keep calling the same handlers during MVP.

### Post-MVP order (unchanged)

```text
Phase 5  Tool Registry (formalize what MVP already exposes)
Phase 6  AI Orchestrator (structured decisions)
Phase 7  Context-aware conversational questions
Phase 8  Chat workflow UX (progress bar, tool cards, pending-decision UI)
Phase 9  Connect analysis readiness gates
```

---

# Target Architecture

Aim for this conceptual architecture:

```text
┌─────────────────────────────────┐
│          Next.js Chat UI         │
│                                 │
│ User + File/API/Database        │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│         FastAPI Chat API         │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│         AI Orchestrator          │
│                                 │
│ Understand context              │
│ Read workflow state             │
│ Decide next action              │
│ Ask user OR propose tool call   │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│         Workflow Engine          │
│                                 │
│ Validate action                 │
│ Check dependencies              │
│ Prevent invalid transitions     │
│ Prevent duplicate execution     │
│ Enforce confirmation rules      │
└───────────────┬─────────────────┘
                ↓
        ┌───────┼────────┐
        ↓       ↓        ↓
     Prepare  Cleaning  Mapping
        │       │        │
        └───────┼────────┘
                ↓
            Validation
                ↓
             Analysis
                ↓
       KPI / Findings / Report
```

---

# Step 1 — Break the Existing Pipeline into Independent Tools

Refactor existing logic so these operations can be executed independently:

```python
inspect_source(...)
prepare_data(...)
clean_data(...)
map_schema(...)
validate_data(...)
analyze_data(...)
```

Do not duplicate existing business logic if equivalent functions already exist.

Wrap existing modules when possible.

Each tool should:

1. receive explicit structured input;
2. perform one bounded responsibility;
3. persist relevant artifacts/results;
4. return a structured result;
5. never silently trigger every downstream step.

Example common result shape:

```python
class ToolResult(BaseModel):
    status: str
    summary: str
    findings: list
    warnings: list
    artifacts: dict
    suggested_next_actions: list[str]
```

Example:

```json
{
  "status": "completed",
  "summary": "Cleaning completed",
  "findings": [
    {
      "type": "duplicate_rows",
      "count": 147
    },
    {
      "type": "missing_value",
      "column": "customer_code",
      "count": 1380,
      "percent": 3.2
    }
  ],
  "warnings": [],
  "artifacts": {
    "cleaning_report_id": "cln_001"
  },
  "suggested_next_actions": [
    "map_schema"
  ]
}
```

Keep tool output compact and structured so the LLM does not need the entire dataset.

---

# Step 2 — Introduce Source Inspection

When a new file/API/database source is attached, do NOT immediately execute the entire ETL-clean-map-analysis process.

Initial flow:

```text
Receive source
→ Preserve raw source
→ Create source record
→ Create workflow
→ inspect_source()
```

`inspect_source()` should be lightweight and non-destructive.

It may inspect:

* source type
* sheets/tables/endpoints
* row count where practical
* column count
* schema
* sample rows
* detected data types
* missing-value percentages
* duplicate indicators
* date formats
* possible identifiers
* possible metrics
* possible dimensions
* suspicious mixed types
* potential relationships
* API pagination/schema details
* database table/schema metadata

It must not automatically clean or permanently alter the source.

Example inspection result:

```json
{
  "source_type": "excel",
  "rows": 42871,
  "columns": 11,
  "detected_columns": [
    {
      "name": "InvoiceDate",
      "type": "date",
      "confidence": 0.92
    },
    {
      "name": "SKU",
      "type": "string"
    },
    {
      "name": "Qty",
      "type": "numeric"
    }
  ],
  "issues": [
    {
      "type": "mixed_date_format",
      "column": "InvoiceDate"
    }
  ]
}
```

The orchestrator should use this result to determine what to ask or execute next.

---

# Step 3 — Persist Workflow State

Create or adapt persistent workflow entities.

**Reuse-first:** start from `data_setup_sessions` (see **Bridge — Current System to Target Architecture**).
Only add separate `analysis_workflows` tables if the session model cannot support step-level retry, stale invalidation, and orchestrator resume.

Suggested tables/models:

## analysis_workflows

Fields approximately:

```text
id
user_id
source_id
status
current_step
next_action
context jsonb
created_at
updated_at
```

## workflow_steps

Fields approximately:

```text
id
workflow_id
step_type
status
input jsonb
output jsonb
requires_confirmation
started_at
completed_at
version
```

Useful step statuses:

```text
pending
ready
awaiting_user
running
completed
failed
skipped
superseded
stale
```

Example state:

```json
{
  "workflow_id": "wf_123",
  "source_id": "src_001",
  "status": "in_progress",
  "current_step": "cleaning",
  "next_action": "resolve_duplicate_policy",
  "steps": {
    "inspect": {
      "status": "completed"
    },
    "prepare": {
      "status": "completed"
    },
    "cleaning": {
      "status": "awaiting_user"
    },
    "mapping": {
      "status": "pending"
    },
    "validation": {
      "status": "pending"
    }
  }
}
```

The system must be able to restore this state when the user sends the next chat message.

---

# Step 4 — Build a Workflow Engine

Do NOT let the LLM call arbitrary Python functions directly.

Create a controlled workflow engine that sits between AI decisions and backend execution.

Responsibilities:

* validate requested tool;
* verify current workflow state;
* verify dependencies;
* ensure the step is allowed;
* enforce confirmation rules;
* prevent loops;
* prevent duplicate execution;
* prevent invalid skipping;
* handle retry;
* mark downstream outputs stale when upstream definitions change.

Suggested structure:

```text
services/
  workflow/
    engine.py
    state.py
    transitions.py
    dependencies.py
    policies.py
```

Possible high-level states:

```text
SOURCE_RECEIVED
INSPECTED
PREPARE_PENDING
PREPARED
CLEANING_PENDING
CLEANED
MAPPING_PENDING
MAPPED
VALIDATION_PENDING
VALIDATED
READY_FOR_ANALYSIS
ANALYSIS_RUNNING
ANALYZED
```

Do NOT require a rigid straight-line pipeline when unnecessary.

Examples:

```text
Inspect
→ Prepare
→ Cleaning skipped
→ Mapping
```

or

```text
Database Inspect
→ Existing trusted mapping found
→ Prepare
→ Validate
```

Skipped steps must include an explicit reason.

Example:

```json
{
  "step": "cleaning",
  "status": "skipped",
  "reason": "No material data quality issues detected"
}
```

---

# Step 5 — Tool Registry

Create a central registry.

Suggested conceptual interface:

```python
TOOLS = {
    "inspect_source": {
        "handler": inspect_source,
        "allowed_states": [...],
        "requires": [],
        "destructive": False
    },
    "prepare_data": {
        "handler": prepare_data,
        "allowed_states": [...],
        "requires": ["inspect"],
        "destructive": False
    },
    "clean_data": {
        "handler": clean_data,
        "allowed_states": [...],
        "requires": ["prepare"],
        "destructive": False
    },
    "map_schema": {
        "handler": map_schema,
        "allowed_states": [...],
        "requires": ["inspect"],
        "destructive": False
    },
    "validate_data": {
        "handler": validate_data,
        "requires": ["mapping"]
    },
    "analyze_data": {
        "handler": analyze_data,
        "requires": ["validation"]
    }
}
```

Adapt this to the existing project conventions.

The Workflow Engine, not the LLM, must determine whether the tool can execute.

---

# Step 6 — AI Orchestrator

Create an AI orchestration layer.

Suggested structure:

```text
services/
  orchestrator/
    orchestrator.py
    context_builder.py
    decision_parser.py
    prompts.py
```

Conceptual flow:

```python
async def handle_chat(workflow, user_message, conversation):
    state = await get_workflow_state(workflow.id)

    context = build_orchestrator_context(
        workflow=state,
        user_message=user_message,
        conversation=conversation
    )

    decision = await llm_decide(context)

    return await workflow_engine.execute_decision(
        workflow=workflow,
        decision=decision
    )
```

Do not expose raw unrestricted LLM text as executable behavior.

Require a structured decision.

---

# Step 7 — LLM Decision Schema

At minimum support these decision types:

```text
ask_user
tool_call
respond
```

Possible models:

```python
class AskUserDecision(BaseModel):
    type: Literal["ask_user"]
    reason: str
    question: str
    options: list | None = None
    context_key: str | None = None

class ToolCallDecision(BaseModel):
    type: Literal["tool_call"]
    tool: str
    arguments: dict
    reason: str

class RespondDecision(BaseModel):
    type: Literal["respond"]
    message: str
```

Example:

```json
{
  "type": "ask_user",
  "reason": "Negative amounts may represent returns and materially affect business meaning.",
  "question": "ยอดติดลบในข้อมูลนี้หมายถึงรายการคืนสินค้าใช่หรือไม่?",
  "options": [
    "ใช่ เป็นสินค้าคืน",
    "ไม่ใช่ เป็นข้อมูลผิดปกติ",
    "ยังไม่แน่ใจ"
  ],
  "context_key": "return_policy"
}
```

Example:

```json
{
  "type": "tool_call",
  "tool": "clean_data",
  "arguments": {
    "profile": "standard"
  },
  "reason": "Preparation is complete and the user confirmed the return policy."
}
```

Reject unknown tool names.

---

# Step 8 — Orchestrator Prompt Principles

The system prompt should follow this philosophy:

```text
You are the MataQorLab Data Workflow Orchestrator.

Your role is to guide users through a governed analytical workflow.

You do NOT:
- calculate business metrics yourself
- directly modify datasets
- invent business definitions
- assume ambiguous business context
- silently discard materially ambiguous records

You may:
- inspect workflow state
- interpret structured tool results
- ask targeted questions
- select an authorized backend tool
- explain completed operations

Core principles:

1. Use backend tools for deterministic data operations.
2. Ask the user only when a decision materially affects data meaning.
3. Do not ask questions that can be safely inferred from the data.
4. Preserve raw data.
5. Never silently discard ambiguous business records.
6. Respect confirmed Data Contract decisions.
7. Avoid rerunning completed steps unless dependencies changed.
8. Prefer the smallest necessary next action.
9. Never bypass workflow dependencies.
10. Computation verification does not imply business truth.
11. Use existing context before asking the user the same question again.
12. Prefer contextual questions based on the actual dataset.
```

The AI should not ask generic ETL/Cleaning/Mapping questions every time.

Questions must adapt to the source.

---

# Step 9 — Context-Aware Conversation

The workflow should feel like an AI Data Analyst collaborating with the Data Owner.

Example:

User uploads:

```text
sales.xlsx
```

Inspection finds:

```text
42,871 rows
11 columns
mixed InvoiceDate format
147 exact duplicate rows
612 negative sales records
```

MataQorLab should NOT say:

```text
Which ETL configuration do you want?
Which cleaning profile do you want?
How should I map all columns?
```

Instead it should say something like:

```text
ผมตรวจพบข้อมูลยอดขาย 42,871 รายการ มี 11 คอลัมน์

InvoiceDate มีรูปแบบวันที่มากกว่า 1 แบบ ผมแนะนำให้ปรับรูปแบบวันที่ให้อยู่ในมาตรฐานเดียวกัน โดยยังคง Raw Data ต้นฉบับไว้
```

After preparation:

```text
Prepare เสร็จแล้ว

พบรายการซ้ำ 147 แถว และยอดติดลบ 612 รายการ
รายการติดลบอาจหมายถึงสินค้าคืนและมีผลต่อความหมายของยอดขาย

ยอดติดลบในชุดนี้หมายถึง Return ใช่ไหม?
```

After user says yes:

```text
Persist Data Contract:
return_policy = include_as_negative
```

Then cleaning tool runs.

Then mapping result may be:

```text
InvoiceDate → transaction_date 99%
SKU → product_code 98%
Qty → quantity 97%
NET_AMT → sales_value 96%
PRICE_LEVEL → unknown 58%
```

The AI should ask only about `PRICE_LEVEL`.

Example:

```text
ผม map ได้ 17 จาก 18 คอลัมน์

เหลือ PRICE_LEVEL ที่ยังไม่แน่ใจ
คอลัมน์นี้หมายถึงระดับราคาของลูกค้าใช่ไหม?
```

Do not ask the user to manually remap every confident column.

---

# Step 10 — Mapping Confidence

Implement or reuse mapping confidence where practical.

Suggested policy:

```text
confidence >= 0.90
→ auto-map unless business-sensitive

0.65–0.89
→ suggest mapping / optionally confirm

< 0.65
→ ask user
```

Do not make these thresholds hardcoded everywhere; centralize policy/configuration.

Mappings should record:

```text
source_column
semantic_role
confidence
source
status
version
```

Possible mapping sources:

```text
automatic
user_confirmed
data_contract
saved_mapping
system_rule
```

---

# Step 11 — Data Preparation vs Cleaning

Keep responsibilities separated.

## Prepare Data

May handle:

* encoding
* sheet selection
* table selection
* header normalization
* column-name normalization
* date parsing
* numeric parsing
* boolean parsing
* JSON flattening
* API pagination mechanics
* source extraction
* safe structural normalization

Avoid business-destructive behavior.

## Cleaning

May handle:

* exact duplicates
* missing data handling
* invalid values
* standardization
* outlier handling
* cleansing profiles
* data quality transformations

Do not automatically remove business-ambiguous rows.

Examples requiring business context:

* negative sales
* cancelled invoices
* returns
* zero quantity
* free items
* unusual price
* duplicate-looking documents
* missing customer
* missing product
* tax-inclusive vs tax-exclusive amount

If data meaning is unclear, pause the workflow and ask.

---

# Step 12 — Reuse Existing Cleaning Profiles

MataQorLab already has cleaning profiles:

```text
Standard      (standard)
Financial     (financial)
Careful       (conservative)
Deep Clean    (aggressive)
```

Reuse them. Use code identifiers in handlers; UX labels only in UI copy.

The orchestrator can recommend a profile based on detected issues, but risky/aggressive behavior must not be silently chosen.

Example:

```text
Standard may be auto-selected for harmless normalization.

Deep Clean should not be automatically applied if it could remove or materially alter business records without explicit policy.
```

---

# Step 13 — Data Contract from Conversation

Do not force users through one large configuration form at the beginning.

Allow Data Contract fields to be collected progressively during conversation.

Examples:

User:

```text
หนึ่งแถวคือสินค้าแต่ละรายการในบิล
```

Persist:

```json
{
  "row_grain": {
    "value": "invoice_line",
    "source": "user_confirmed"
  }
}
```

User:

```text
ยอดติดลบคือสินค้าคืน
```

Persist:

```json
{
  "return_policy": {
    "value": "negative_amount",
    "treatment": "include_as_negative",
    "source": "user_confirmed"
  }
}
```

Possible Data Contract dimensions include:

* data owner
* decision purpose
* row grain
* primary metric definition
* cancellation policy
* return policy
* tax treatment
* reporting-period completeness
* known exceptions
* owner review
* business-specific rules

Version Data Contract changes.

---

# Step 14 — Versioning and Dependency Invalidation

Important governance requirement.

Track versions for important artifacts:

```text
Prepare v1
Cleaning v1
Mapping v1
Data Contract v1
Validation v1
Analysis v1
```

If the user changes an upstream business definition, invalidate only affected downstream outputs.

Example:

User changes:

```text
Return policy:
include_as_negative
→ exclude_from_sales
```

System should determine:

```text
Prepare        still valid
Cleaning       maybe valid
Mapping        valid
Validation     stale
Metric results stale
Analysis       stale
Insights       stale
Reports        stale
```

Then rerun only the required downstream dependencies.

Do not restart ingestion unnecessarily.

Implement a dependency graph or centralized dependency rules.

---

# Step 15 — Retry and Resume

Each step must be independently retryable.

Example:

```text
Prepare      completed
Cleaning     completed
Mapping      failed
Validation   pending
```

Retry only Mapping.

The workflow must survive:

* browser refresh
* backend restart
* temporary worker failure
* user leaving and returning later

Persist enough state to resume.

---

# Step 16 — Long-Running Jobs

Long-running data operations should not block a FastAPI request.

If an existing background-worker mechanism already exists, reuse it.

Otherwise design the workflow so it can support:

```text
AI requests tool
→ Workflow Engine authorizes tool
→ Create job
→ Queue
→ Worker
→ DuckDB/pandas processing
→ Persist result/artifact
→ Mark workflow step completed
→ Next chat turn/orchestration continues
```

Redis can be used if already planned in the project.

Do not make the AI wait synchronously for very large processing jobs if the existing architecture supports workers.

---

# Step 17 — LLM Context

Do not send the full dataset to the LLM.

Build a compact orchestration context.

Example:

```json
{
  "workflow_state": {},
  "source_profile": {},
  "data_quality_summary": {},
  "mapping_summary": {},
  "data_contract": {},
  "latest_tool_result": {},
  "conversation_summary": {}
}
```

For a 1,000,000-row dataset, the LLM may see only something like:

```text
rows: 1,038,291
columns: 24

date_range:
2025-01-01 → 2026-08-06

missing:
customer_code = 2.1%
sales_amount = 0%

duplicates:
1421

mapping:
21 confirmed
2 automatic
1 unresolved

unresolved:
PRICE_LEVEL
```

The deterministic engine continues to own raw data and calculations.

---

# Step 18 — Chat API

Inspect current APIs first and avoid breaking compatibility unnecessarily.

Possible endpoints:

```text
POST /sources
POST /sources/{id}/inspect

POST /workflows
GET /workflows/{id}

POST /workflows/{id}/message
POST /workflows/{id}/actions/{action}
```

However, from the frontend perspective, prefer a simple conversational interface where possible:

```text
POST /chat
```

and backend orchestration handles the workflow.

Do not expose unnecessary workflow complexity to the UI.

---

# Step 19 — Chat UI Workflow Status

Add visible workflow progress in the chat experience.

Example:

```text
sales_2026.xlsx

✓ Source inspected
✓ Prepare
● Cleaning
○ Mapping
○ Validation
○ Analysis
```

The user should not need to manually run every stage.

The AI orchestrates it.

---

# Step 20 — Tool Execution Cards

Where compatible with the current frontend design, add structured UI cards for completed tool execution.

Example:

```text
┌────────────────────────────────┐
│ ✓ Data Cleaning                │
│                                │
│ 42,871 → 42,724 rows          │
│                                │
│ Removed duplicates     147     │
│ Missing amount           0     │
│ Returns retained       612     │
│                                │
│ View Cleaning Report           │
└────────────────────────────────┘
```

This should be backed by real persisted tool output.

Do not rely only on AI-generated prose for operation status.

---

# Step 21 — Database Sources

For database connections, avoid immediately ingesting the entire database.

Preferred workflow:

```text
Connect database
→ Inspect schemas/tables
→ Detect likely relevant tables
→ Ask/select business scope if necessary
→ Inspect relationships
→ Extract selected scope
→ Prepare
→ Clean
→ Map
→ Validate
```

Example:

```text
พบ 26 tables

ตารางที่มีแนวโน้มเกี่ยวข้องกับยอดขาย:
- sales_header
- sales_detail
- customer
- product
```

If a relationship has an issue:

```text
sales_header and sales_detail appear to join by doc_no,
but 84 detail rows have no matching header.
```

Ask the user only if the handling materially changes meaning.

---

# Step 22 — REST API Sources

For APIs, preferred workflow:

```text
Register API source
→ inspect endpoint / sample response
→ identify pagination
→ identify grain
→ identify date scope
→ ingest authorized scope
→ prepare
→ clean
→ map
→ validate
```

Do not fetch arbitrarily huge histories when a narrower scope is sufficient.

Persist API/source configuration where the current system already supports source sync.

---

# Step 23 — Assurance

Preserve MataQorLab's existing separation between:

```text
Computation
Data readiness
Business context
```

Do not collapse these into a single “verified” state.

For example:

```text
Computation verified
```

must mean:

```text
The calculation is consistent with the provided data and approved formula.
```

It must NOT mean:

```text
The business data is necessarily true.
```

Final readiness may look like:

```text
Computation readiness: Verified
Data readiness: Ready
Business context: Confirmed
```

Keep this principle throughout the workflow.

---

# Step 24 — Suggested Project Structure

Do not blindly create this if the existing codebase has better conventions.

Use it as a target reference:

```text
backend/
│
├── api/
│   ├── chat.py
│   ├── sources.py
│   └── workflows.py
│
├── services/
│   ├── orchestrator/
│   │   ├── orchestrator.py
│   │   ├── context_builder.py
│   │   ├── decision_parser.py
│   │   └── prompts.py
│   │
│   ├── workflow/
│   │   ├── engine.py
│   │   ├── state.py
│   │   ├── transitions.py
│   │   ├── dependencies.py
│   │   └── policies.py
│   │
│   └── tools/
│       ├── registry.py
│       ├── inspect_source.py
│       ├── prepare_data.py
│       ├── clean_data.py
│       ├── map_schema.py
│       ├── validate_data.py
│       └── analyze_data.py
│
├── models/
│   ├── workflow.py
│   ├── workflow_step.py
│   └── tool_result.py
│
└── workers/
    ├── data_worker.py
    └── jobs.py
```

Adapt naming to the project.

---

# Step 25 — Expected End-to-End UX

Example final behavior:

User:

```text
[sales.xlsx]
ช่วยวิเคราะห์ยอดขายให้หน่อย
```

System:

```text
Raw source saved
→ workflow created
→ inspect_source executed
```

MataQorLab:

```text
ตรวจข้อมูลแล้ว

ข้อมูลมี:
• 82,421 rows
• 18 columns
• ช่วงวันที่ Jan–Jul 2026

พบรูปแบบวันที่ 2 แบบ
ผมแนะนำให้ normalize วันที่ก่อน โดยไม่แก้ Raw Data ต้นฉบับ
```

User:

```text
ทำเลย
```

System:

```text
prepare_data()
```

MataQorLab:

```text
Prepare เสร็จแล้ว ✓

ตอน Cleaning พบยอดติดลบ 327 รายการ
จากโครงสร้างข้อมูล รายการเหล่านี้อาจเป็นการคืนสินค้า

ยอดติดลบในชุดนี้หมายถึง Return ใช่ไหม?
```

User:

```text
ใช่
```

System:

```text
Persist Data Contract decision
→ clean_data()
```

MataQorLab:

```text
Cleaning เสร็จแล้ว ✓

ผม map ได้ 17 จาก 18 columns

เหลือ PRICE_LEVEL ที่ยังตีความไม่แน่ชัด
PRICE_LEVEL หมายถึงระดับราคาของลูกค้าใช่ไหม?
```

User:

```text
ใช่
```

System:

```text
persist mapping
→ map_schema()
→ validate_data()
```

MataQorLab:

```text
ข้อมูลพร้อมสำหรับ Analysis แล้ว ✓

Computation readiness: Verified
Data readiness: Ready
Business context: Confirmed

Business definitions currently in use:
• Return = negative transaction
• Price Level = customer price level
• Row grain = one product line per invoice
```

Only after this should the system proceed into analytics/KPI/findings/insight generation.

---

# Implementation Order

Do this incrementally.

See **Bridge — Current System to Target Architecture** for current-module mapping, API inventory, migration plan, and MVP boundaries.

## Phase 1 — Inspect Existing System

Before editing:

1. inspect existing ingestion;
2. find current ETL/prepare implementation;
3. find cleaning modules and cleaning profiles;
4. find mapping logic;
5. find validation/data-quality logic;
6. find chat orchestration;
7. find source/database models;
8. find Data Contract implementation;
9. find current analysis pipeline;
10. find worker/queue/job handling.

Produce a short architectural assessment.

Clearly identify:

```text
Reuse as-is
Wrap/refactor
New module needed
Potential migration risk
```

Do not implement duplicate systems.

## Phase 2 — Separate Existing Pipeline

Make:

```text
inspect
prepare
clean
map
validate
```

independently executable and testable.

Preserve existing pipeline behavior where possible.

## Phase 3 — Persist Workflow State

Implement workflow + workflow-step persistence.

Add migration(s) if necessary.

## Phase 4 — Workflow Engine

Implement:

* state transition checks
* dependency checks
* retries
* skip state
* stale state
* duplicate protection
* authorization hooks

## Phase 5 — Tool Registry

Expose existing backend operations through the controlled registry.

## Phase 6 — AI Orchestrator

Add structured LLM decisions.

Do not allow arbitrary code/tool calls.

## Phase 7 — Conversational Context Decisions

Add targeted handling first for:

* mixed date formats
* duplicates
* missing values
* negative transactions / returns
* cancellations
* ambiguous mappings
* row grain
* primary metric definitions
* tax treatment if relevant

## Phase 8 — Frontend Workflow UX

Add:

* workflow state indicator
* pending-user-decision UI
* tool execution cards
* step status
* failed-step retry UI where appropriate

## Phase 9 — Connect Analysis

Only allow analysis when workflow readiness requirements are met.

---

# Testing Requirements

Add or update tests for at least:

1. new source creates workflow;
2. source inspection completes without cleaning;
3. preparation can run independently;
4. cleaning can pause for user context;
5. user response resumes the same workflow;
6. invalid tool transition is rejected;
7. completed step is not rerun unnecessarily;
8. failed mapping can retry without rerunning cleaning;
9. changed Data Contract invalidates affected downstream steps;
10. confident mapping can auto-map;
11. ambiguous mapping requests user input;
12. raw source remains unchanged;
13. workflow persists across requests;
14. analysis cannot run before required validation;
15. LLM cannot execute unknown tools;
16. deterministic calculations remain outside the LLM.

If there is an existing test framework, use it.

---

# Critical Constraints

* Do not replace deterministic analysis with LLM-generated calculations.
* Do not send full datasets to the LLM.
* Do not silently delete ambiguous business records.
* Do not destroy raw data.
* Do not create a second duplicate ETL system if one already exists.
* Do not hardcode the conversation to always ask ETL → Cleaning → Mapping questions.
* The next action must depend on the actual source profile and workflow state.
* Avoid unnecessary user questions.
* Ask only when a decision materially affects meaning, correctness, governance, or destructive behavior.
* Reuse confirmed user/business context.
* Persist decisions.
* Maintain auditability.
* Prefer incremental code changes over a large rewrite.

---

# First Task

Start by inspecting the current MataQorLab codebase.

Read **Bridge — Current System to Target Architecture** first, then validate or correct its mappings during inspection.

Do NOT immediately refactor everything.

First return a concise implementation assessment containing:

```text
1. Current pipeline flow
2. Existing files/modules involved
3. Which existing components can be reused
4. Which components need refactoring
5. Which new components are needed
6. Database migration requirements
7. API changes
8. Frontend changes
9. Risks / compatibility concerns
10. Recommended implementation order
```

Then proceed with the implementation incrementally.

When modifying the code, keep the project runnable after each logical phase.

Use existing naming conventions and architecture wherever reasonable.

---

# Phase 1 Assessment Results

**Date:** 2026-08-07  
**Status:** Complete — ready for Phase 2  
**Scope:** Inspect only; no runtime behavior changed.

## 1. Current pipeline flow

```text
User attaches File / API / SQL / Cloud in Chat
        ↓
POST /data-setup/scan
  → load_setup_handle (sample)
  → build_scan_result
  → create/update data_setup_sessions
        ↓
DataSetupCopilot wizard (Chat.tsx card)
  scan → structure → mapping → cleaning → business_context → review
  PATCH /data-setup/{id} (draft)
  POST /data-setup/{id}/preview (bounded clean preview)
        ↓
POST /data-setup/{id}/approve
  → validate_data_contract
  → status=approved
  → BackgroundTasks and/or data_setup_worker claim
        ↓
process_data_setup_session (MONOLITH)
  → load full source
  → materialize non-file snapshot
  → insert etl_recipes
  → execute_etl_recipe (clean + prepare + write)
  → register_completed_dataset_version
  → session status=ready
        ↓
POST /chat or /chat/stream
  → _require_user_approved_mapping
  → _require_ready_data_setup
  → ChatContextBuilder.prepare
  → analytics + analysis_agent + findings + decision_assurance
  → LLM stream
```

**Independence today**

| Stage | Independent? | How |
|---|---|---|
| Inspect / scan | Yes | `POST /data-setup/scan`, `build_scan_result` |
| Draft mapping / contract | Yes | `PATCH /data-setup/{id}` |
| Clean preview | Yes | `POST /data-setup/{id}/preview`, `POST /etl/preview` |
| Full prepare / clean / publish | No | Only via approve → `process_data_setup_session` |
| Map as standalone tool | No | Embedded in wizard + recipe JSON |
| Validate as standalone tool | Partial | `validate_data_contract` called on preview/approve |
| Analyze | After ready only | Chat gates |

## 2. Existing files/modules involved

### Backend — setup / ETL

| Path | Role |
|---|---|
| `backend/app/services/data_setup.py` | Scan, preview, load handles, `process_data_setup_session` |
| `backend/app/services/data_setup_worker.py` | Claim + process approved sessions |
| `backend/app/services/data_cleaning.py` | Profiles + `clean_dataframe` / DuckDB clean / `prepare_handle_for_analysis` |
| `backend/app/services/etl_pipeline.py` | Recipe normalize, contract validate, apply recipe, cleaning preview |
| `backend/app/services/etl_execution.py` | `execute_etl_recipe`, pipeline runs |
| `backend/app/services/dataset_engine.py` | `DatasetHandle`, DuckDB/pandas engine |
| `backend/app/services/dataset_loader.py` | Load from Storage |
| `backend/app/services/dataset_catalog.py` | Version registration / lineage |
| `backend/app/services/domain_analytics.py` | `infer_semantic_roles`, domain KPIs |
| `backend/app/services/column_profile.py` | Column profiling |
| `backend/app/services/external_api.py` | API connection fetch |
| `backend/app/services/sql_execution.py` | SQL source load |
| `backend/app/services/cloud_dataset.py` | Cloud source load |
| `backend/app/api/routes.py` | `/data-setup/*`, `/etl/preview`, chat gates |

### Backend — chat / analysis

| Path | Role |
|---|---|
| `backend/app/services/chat/service.py` | Facade |
| `backend/app/services/chat/context_builder.py` | Full chat prepare pipeline |
| `backend/app/services/chat/ingest.py` | Parallel ingest path for chat attachments |
| `backend/app/services/chat/stream_handler.py` | SSE / completion |
| `backend/app/services/chat/agent_bridge.py` | Agent analytics entry |
| `backend/app/services/analysis_agent.py` | Autonomous analysis loop |
| `backend/app/services/analytics_service.py` | Base analytics |
| `backend/app/services/decision_assurance.py` | Computation / data readiness / business context |

### Frontend

| Path | Role |
|---|---|
| `src/features/chat/DataSetupCopilot.tsx` | Wizard UI |
| `src/views/Chat.tsx` | Embeds wizard; scan/cancel/ready handoff |
| `src/features/chat/dataSetupErrors.js` | API error formatting |

### Database (Supabase)

| SQL / table | Role |
|---|---|
| `adaptive_data_setup_copilot.sql` → `data_setup_sessions` | Setup state machine |
| `etl_workflows.sql` → `etl_recipes`, `etl_pipeline_runs` | Recipes + runs |
| `p1_unified_dataset_catalog.sql` → `dataset_versions` / catalog | Published outputs |
| Claim RPCs | `claim_data_setup_session(s)` (service_role) |

### Tests already covering this area

* `backend/tests/test_data_setup.py`
* `backend/tests/test_data_setup_worker.py`
* `backend/tests/test_adaptive_data_setup_migration.py`
* `backend/tests/test_chat_mapping_gate.py`
* `backend/tests/test_etl_pipeline.py`
* `backend/tests/test_etl_execution_compatibility.py`
* `backend/tests/test_decision_assurance.py`
* `src/features/chat/dataSetupErrors.test.js`

## 3. Which existing components can be reused

**Reuse as-is**

* Cleaning engines + profiles (`standard` / `financial` / `conservative` / `aggressive`)
* `validate_data_contract` / `normalize_data_contract`
* `execute_etl_recipe` + ETL run persistence
* Dataset catalog / version registration / lineage
* Data setup worker claim loop + RPCs
* Chat gates `_require_ready_data_setup` / `_require_user_approved_mapping`
* Decision assurance packet (keep Computation ≠ Data readiness ≠ Business context)
* Analysis path after ready (`analytics_service`, `analysis_agent`, domain KPIs)
* Existing `/data-setup/*` public API shapes (compatibility)

**Wrap as tools (Phase 2)**

* `build_scan_result` + `load_setup_handle` → `inspect_source`
* `prepare_handle_for_analysis` / `DatasetHandle.prepare_for_analysis` → `prepare_data`
* `clean_dataframe` / recipe apply / preview → `clean_data`
* `infer_semantic_roles` + session `column_mapping` → `map_schema`
* `validate_data_contract` + readiness checks → `validate_data`
* Post-ready chat analytics entry → `analyze_data` (Phase 9 gate only; not MVP)

## 4. Which components need refactoring

| Component | Why |
|---|---|
| `process_data_setup_session` | Monolith; no mid-stage resume/retry; must become sequenced tool calls |
| Wizard ↔ backend contract | Stages exist as UI steps + JSON blobs, not as executable tool boundaries |
| Dual ingest paths | `data_setup.load_setup_handle` vs `chat/ingest.DataIngestService` can drift |
| Dual mapping stores | Session `column_mapping` vs `column_mappings_memory` (chat modal) |
| `ChatContextBuilder.prepare` | Large orchestration hub; later host for orchestrator, not MVP rewrite |

## 5. Which new components are needed

### MVP (Phase 2–4)

| New component | Purpose |
|---|---|
| `backend/app/services/tools/*.py` | Thin wrappers with shared `ToolResult` shape |
| `backend/app/services/tools/registry.py` | Name → handler + requires + allowed states |
| `backend/app/services/workflow/state.py` | Read/write step state on/evolved from sessions |
| `backend/app/services/workflow/engine.py` | Authorize transitions, deps, skip, stale, retry |
| `backend/app/services/workflow/dependencies.py` | Dependency / invalidation graph |
| Optional `workflow_steps` child table | Per-step input/output/status/version if session JSONB is insufficient |
| Internal test harness | Invoke tools by name without LLM |

### Post-MVP (Phase 5–9)

| New component | Purpose |
|---|---|
| `services/orchestrator/*` | Structured `ask_user` / `tool_call` / `respond` |
| Chat workflow progress UI + tool cards | Phase 8 |
| Conversational decision handlers | Phase 7 |

**Do not create:** parallel `analysis_workflows` table set until session model proves insufficient.

## 6. Database migration requirements

**Phase 3 preference (confirmed by inspection):** evolve `data_setup_sessions`.

Recommended migration(s):

1. Add nullable fields if missing: `next_action`, richer `context` / step-status JSON, optional step versions.
2. Prefer child table:

```text
workflow_steps (
  id, data_setup_session_id, step_type, status,
  input jsonb, output jsonb, requires_confirmation,
  version, started_at, completed_at, reason
)
```

3. Keep existing session statuses and `current_step` for wizard compatibility during coexistence.
4. No change required to `etl_recipes` / `etl_pipeline_runs` / `dataset_versions` for MVP.
5. Do **not** introduce `analysis_workflows` in MVP.

## 7. API changes

**MVP:** no new public REST surface required.

* Keep `/data-setup/scan|resume|{id}|preview|approve|cancel` stable.
* Optionally call tool wrappers from existing route handlers (same responses).
* Add internal/test-only tool invoke path if useful (not product UI).

**Post-MVP:**

* Prefer orchestration inside `POST /chat` rather than new `/workflows/{id}/message`.
* Wire frontend to `GET /data-setup/resume` (API exists; UI unused today).

## 8. Frontend changes

**MVP:** none required for behavior change.

* Keep `DataSetupCopilot` as primary setup UX.
* Keep chat blocked until session `ready`.

**Later (Phase 7–8):**

* Conversational questions + tool execution cards in chat.
* Feature-flag wizard → Advanced setup.
* Call `/data-setup/resume` on Chat mount for abandoned sessions.

**Bridge correction:** resume API exists backend-only; frontend gap is confirmed.

## 9. Risks / compatibility concerns

| Risk | Severity | Mitigation |
|---|---|---|
| Breaking `/data-setup/*` response shapes | High | Wrap behind existing handlers; contract tests |
| Dual dispatch (BackgroundTasks + worker) race | Medium | Keep claim RPC; tools must be idempotent |
| Preview sample ≠ full DuckDB clean drift | Medium | Shared clean entrypoint for preview + full |
| Dual mapping stores diverge | Medium | Session mapping is source of truth for setup; sync memory later |
| Agent session bypasses ready gate | Medium | Document; do not widen bypass |
| Creating second workflow table system | High | Evolve sessions first (Bridge rule) |
| Large rewrite of chat before tools exist | High | MVP stops at Phase 4 |
| Uncommitted-style coupling of recipe approve to full reprocess | Medium | Phase 2–4 enable step retry without full restart |

## 10. Recommended implementation order

Confirmed MVP = Phase 1–4. Next steps:

```text
Phase 2 — Separate pipeline into tools
  1. Define ToolResult schema
  2. tools/inspect_source.py  (wrap build_scan_result)
  3. tools/prepare_data.py
  4. tools/clean_data.py      (preview + full apply paths)
  5. tools/map_schema.py
  6. tools/validate_data.py
  7. Refactor process_data_setup_session to call tools in sequence
     (behavior-compatible; wizard still works)
  8. Unit tests per tool (extend test_data_setup.py)

Phase 3 — Persist step state
  1. Migration: workflow_steps child of data_setup_sessions
     OR step-status JSONB fields
  2. state.py read/write helpers
  3. Persist each tool result; support resume mid-pipeline

Phase 4 — Workflow engine
  1. transitions + dependencies + policies
  2. Reject invalid tool calls
  3. Skip / stale / retry without rerunning completed upstream
  4. Tests from Testing Requirements items 1–9, 12–14

STOP for MVP. Do not start orchestrator / wizard replacement yet.
```

## Bridge validation

Bridge mappings in this document are **validated** with these corrections/notes:

1. Resume endpoint exists (`GET /data-setup/resume`) but is **not used by Chat UI**.
2. Clean preview is already independently callable; full clean is not.
3. `POST /etl/preview` is an additional existing preview surface beyond `/data-setup/{id}/preview`.
4. Mapping memory table is a **parallel** store to session mapping — unify later, do not treat as setup source of truth.
5. Cleaning profile code IDs remain `conservative` / `aggressive` (UX: Careful / Deep Clean).
6. Default persistence path remains **evolve `data_setup_sessions`**, not new `analysis_workflows`.

## Phase 1 exit criteria

* [x] Current pipeline documented
* [x] Reuse / wrap / new classified
* [x] DB migration preference decided
* [x] API compatibility constraints listed
* [x] MVP boundary reconfirmed (stop after Phase 4)
* [x] Proceed to Phase 2 tool wrappers (next task)

---

# Phase 2 Results

**Date:** 2026-08-07  
**Status:** Complete — STOP (do not start Phase 3)  
**Scope:** Independent tool wrappers + compatibility sequencer; no orchestrator; no workflow_steps migration; no wizard replacement.

## 1. Files added

```text
backend/app/services/tools/__init__.py
backend/app/services/tools/types.py
backend/app/services/tools/inspect_source.py
backend/app/services/tools/prepare_data.py
backend/app/services/tools/clean_data.py
backend/app/services/tools/map_schema.py
backend/app/services/tools/validate_data.py
backend/app/services/tools/finalize.py
backend/app/services/tools/registry.py
backend/tests/test_setup_tools.py
```

## 2. Files modified

```text
backend/app/services/data_setup.py       — process_data_setup_session → tool sequencer
backend/app/services/etl_execution.py    — extract create_etl_run + publish_transformed_handle
flow.md                                  — this section
```

Public `/data-setup/*` routes and chat gates were **not** intentionally changed.

## 3. Tool interfaces created

| Tool | Entry | Modes / notes |
|---|---|---|
| `inspect_source` | `tools.inspect_source` | Reuses session `scan_result` when present |
| `prepare_data` | `tools.prepare_data` / `run_prepare_data` | Materialize raw source only |
| `clean_data` | `tools.clean_data` / `run_clean_data` | `mode=preview` \| `mode=apply` |
| `map_schema` | `tools.map_schema` | Session mapping authoritative |
| `validate_data` | `tools.validate_data` | Contract readiness; not computation assurance |
| `finalize` (internal) | `tools.finalize_data_setup` | Publish ownership only |

Shared contract: `ToolResult` in `tools/types.py`  
Optional registry: `tools/registry.py` (`TOOL_HANDLERS`, no auth engine)

## 4. Original functions reused by each tool

| Tool | Reuses |
|---|---|
| `inspect_source` | `load_setup_handle`, `build_scan_result` |
| `prepare_data` | `load_setup_handle`, `load_handle_from_storage`, `_materialize_source_handle` |
| `clean_data` preview | `preview_setup_rows` → `clean_dataframe` + `build_cleaning_preview` |
| `clean_data` apply | `DatasetHandle.apply_standard_clean` → `clean_dataframe` / `clean_handle_duckdb` (+ recipe apply) |
| `map_schema` | `infer_semantic_roles` (fallback only); session `column_mapping` |
| `validate_data` | `normalize_data_contract`, `validate_data_contract` |
| `finalize` | `create_etl_run`, `publish_transformed_handle`, `register_completed_dataset_version`, `apply_mapping_clean`, `apply_business_contract` |

## 5. Transformation ownership

| Transformation | Owner |
|---|---|
| Bounded sample load + scan profile | `inspect_source` |
| Full source load | `prepare_data` |
| Non-file raw parquet materialization | `prepare_data` (`_materialize_source_handle`) |
| Cleaning profile rules (dedupe/empty/currency/dates/recipe apply) | `clean_data` |
| Semantic role assignment / mapping summary | `map_schema` |
| Mapping type coercion after clean | `finalize.apply_post_clean_semantics` (`apply_mapping_clean`) |
| Business contract row transforms | `finalize.apply_post_clean_semantics` (`apply_business_contract`) |
| Contract/readiness evaluation | `validate_data` |
| ETL recipe insert + run audit | `finalize` |
| Output parquet write / storage upload | `finalize` → `publish_transformed_handle` |
| Dataset version + lineage registration | `finalize` → `register_completed_dataset_version` |
| Session `ready` | `finalize` |
| Schedule/manual ETL convenience path | `execute_etl_recipe` still calls `prepare_for_analysis` (clean+map+contract) then publish — **not** used by data-setup sequencer |

**Important finding from Step 1 inspection:**  
`DatasetHandle.prepare_for_analysis` previously coupled clean + mapping coercion + business contract. Phase 2 data-setup path no longer calls it when `cleaned_handle` is supplied; cleaning runs once via `clean_data`.

Profile-based date/number coercion remains inside cleaning engines (existing behavior) — owned by `clean_data`, not duplicated in `prepare_data`.

## 6. process_data_setup_session before/after

### BEFORE

```text
process_data_setup_session
 ├─ load / materialize source
 ├─ insert etl_recipes
 └─ execute_etl_recipe
     ├─ load_handle_from_storage
     ├─ validate_data_contract
     ├─ handle.prepare_for_analysis   ← clean + map coerce + contract
     ├─ write parquet outputs
     ├─ update etl_pipeline_runs
     └─ (caller) register_completed_dataset_version → ready
```

### AFTER

```text
process_data_setup_session
 ├─ inspect_source
 │   └─ reuse scan_result OR build_scan_result(load_setup_handle sample)
 ├─ prepare_data / run_prepare_data
 │   └─ load_handle_from_storage OR load_setup_handle + _materialize_source_handle
 ├─ map_schema
 │   └─ session column_mapping (+ suggested_mapping metadata)
 ├─ validate_data
 │   └─ validate_data_contract / normalize_data_contract
 ├─ clean_data / run_clean_data(mode=apply)
 │   └─ DatasetHandle.apply_standard_clean
 │       └─ clean_dataframe | clean_handle_duckdb (+ apply_recipe_*)
 └─ finalize_data_setup
     ├─ insert etl_recipes
     ├─ create_etl_run
     ├─ apply_post_clean_semantics
     │   ├─ apply_mapping_clean
     │   └─ apply_business_contract
     ├─ publish_transformed_handle
     ├─ register_completed_dataset_version
     └─ session status = ready
```

## 7. Publish/finalize ownership

**Sole publisher for data-setup:** `finalize_data_setup`  
`prepare_data` and `clean_data` never write business-data outputs, never insert dataset versions, never mark session ready.

Schedule/manual ETL remains on `execute_etl_recipe` (load → `prepare_for_analysis` → `publish_transformed_handle`).

## 8. Compatibility notes

* Wizard (`DataSetupCopilot`) unchanged
* `/data-setup/*` and `/etl/preview` response contracts unchanged
* Chat gates `_require_ready_data_setup` / `_require_user_approved_mapping` unchanged
* Early return when session `status == ready` preserved (BackgroundTasks + worker duplicate dispatch)
* Claim RPCs untouched
* Cleaning profile IDs unchanged: `standard` / `financial` / `conservative` / `aggressive`
* Dual ingest (`data_setup` vs `chat/ingest`) and dual mapping memory **not** consolidated (follow-up)

## 9. Remaining coupling

| Coupling | Status | Phase 3 action |
|---|---|---|
| Sequencer still in-process; no persisted per-tool step state | Expected | `workflow_steps` / step JSON |
| `validate_data` `needs_review` does not pause approve path (same as pre-Phase-2 soft contract) | Compatibility | Engine confirmation rules |
| Mapping coercion + business contract live in finalize, not map_schema/validate | Documented | Optional clearer tool split |
| `execute_etl_recipe` still uses combined `prepare_for_analysis` for schedules | Intentional | Optionally adopt tool sequence later |
| Private helpers (`_materialize_source_handle`, `_safe_text`) imported by tools | Acceptable | Promote to public helpers if needed |
| Tool results not yet persisted on session | Expected | Phase 3 |

## 10. Test results

Command:

```text
pytest tests/test_setup_tools.py tests/test_data_setup.py \
  tests/test_data_setup_worker.py tests/test_etl_execution_compatibility.py \
  tests/test_chat_mapping_gate.py tests/test_etl_pipeline.py -q
```

```text
passed:  32
failed:  0
skipped: 0
```

New coverage in `test_setup_tools.py`: tool isolation, no-publish guarantees, scan reuse, preview/apply clean, mapping/validate independence, ToolResult compactness.

## 11. Phase 3 readiness

Ready to start Phase 3 when instructed:

* Evolve `data_setup_sessions` and/or add `workflow_steps` child table
* Persist each tool result / status for resume
* Do **not** start orchestrator or wizard replacement yet

## Phase 2 exit criteria

* [x] ToolResult shared contract exists
* [x] inspect_source has an independent boundary
* [x] prepare_data has an independent boundary
* [x] clean_data has an independent boundary
* [x] map_schema has an independent boundary
* [x] validate_data has an independent boundary
* [x] prepare and clean transformations are not duplicated (data-setup path)
* [x] dataset publication ownership is explicit (`finalize_data_setup`)
* [x] process_data_setup_session delegates to tool boundaries
* [x] existing wizard behavior still works (API surface unchanged)
* [x] existing `/data-setup/*` API contracts remain compatible
* [x] ready/chat gates remain intact
* [x] relevant tests pass (32)
* [x] flow.md contains Phase 2 Results

**STOP.** Awaiting instruction before Phase 3.

---

# Phase 3 Results

**Date:** 2026-08-07  
**Status:** Complete — STOP (do not start Phase 4)  
**Scope:** Persist `workflow_steps`, resume-safe sequencer integration, clean intermediate artifact, finalize idempotency. No orchestrator / dependency engine / wizard replacement.

## 1. Files added

```text
backend/supabase/workflow_steps.sql
backend/app/services/workflow/__init__.py
backend/app/services/workflow/models.py
backend/app/services/workflow/state.py
backend/app/services/workflow/artifacts.py
backend/tests/test_workflow_steps_migration.py
backend/tests/test_workflow_state.py
```

## 2. Files modified

```text
backend/app/services/data_setup.py          — sequencer persistence + resume
backend/app/services/tools/finalize.py      — publish idempotency + cleaned artifact load
backend/app/api/routes.py                   — additive optional workflow metadata on resume
backend/supabase/README.md                  — migration order entry 27
flow.md                                     — this section
```

## 3. Database migration

`backend/supabase/workflow_steps.sql`

* Child table `workflow_steps` → `data_setup_sessions(id)` ON DELETE CASCADE
* Additive session columns: `next_action`, `last_failed_step` (summary cache only)
* Unique history key: `(data_setup_session_id, step_type, version, attempt)`
* Indexes on session, status, step_type
* RLS: authenticated SELECT only via owning session `user_id`; writes service_role only
* RPC `begin_workflow_step(...)` service_role-only atomic begin/reclaim

## 4. Workflow step schema

```text
id, data_setup_session_id, step_type, status,
version, attempt, input jsonb, output jsonb,
reason, error_code, error_message, requires_confirmation,
started_at, completed_at, created_at, updated_at
```

Canonical `step_type` values (not ordered by DB constraint):

```text
inspect | prepare | map | validate | clean | finalize
```

## 5. Status model

Centralized in `workflow/models.py`:

```text
pending, ready, running, awaiting_user,
completed, failed, skipped, stale, superseded
```

## 6. State service

`backend/app/services/workflow/state.py`

* `get_workflow_steps` / `get_latest_step` / `get_resume_state`
* `begin_step` (RPC + Python fallback)
* `complete_step` / `fail_step` / `skip_step` / `mark_step_awaiting_user`
* `execute_persisted_tool_step` persistence wrapper
* `tool_result_to_output` compact serialization
* `update_session_summary` for next_action / last_failed_step

## 7. Tool persistence integration

```text
process_data_setup_session
  ↓
for each tool via execute_persisted_tool_step
  begin_step → running
  tool executes
  complete_step(output=ToolResult) | fail_step(...)
```

Compatibility sequencer order remains:

```text
inspect → prepare → map → validate → clean → finalize
```

Order is **not** a DB constraint.

## 8. Artifact persistence / resume strategy

| Step | Persisted result | Restart-safe | Rerun required | Resume source |
|------|------------------|--------------|----------------|---------------|
| inspect | ToolResult (+ session `scan_result`) | Yes | No | `scan_result` / step output |
| prepare | ToolResult + `dataset_key` | Yes | No | step artifacts / storage key |
| map | ToolResult + mapping | Yes | No | session `column_mapping` + step output |
| validate | ToolResult + contract readiness | Yes | No | re-evaluable from session recipe; completed output reused |
| clean | ToolResult + `cleaned_artifact_key` parquet | Yes* | No if artifact exists | `data_setup_{session}_cleaned_v{n}.parquet` |
| finalize | ToolResult + publish refs | Yes | No if ready/partial publish | session `output_file` / `dataset_version_id` / step output |

\*Clean is restart-safe **after** Phase 3 artifact persistence. If a legacy completed clean step lacks `cleaned_artifact_key`, sequencer bumps version and reruns clean once.

Internal cleaned parquet is **not** a published DatasetVersion.

## 9. Retry behavior — attempt vs version

* **Attempt:** same logical version retried after failure (`clean v1 attempt 1 failed` → `attempt 2`)
* **Version:** bumped when forcing a new logical result (e.g. completed clean without reconstructable artifact → `bump_version=True`)

Encoded in schema now so Phase 4 need not rewrite tables.

## 10. Idempotency behavior

* Session `status == ready` → early return (unchanged)
* `finalize_data_setup` reuses existing ready / partial publish (`output_file` + `dataset_version_id`) without creating a second dataset version
* Reuses existing `recipe_id` / `run_id` on session when present
* `begin_workflow_step` returns existing completed/skipped/fresh-running rows to avoid double execution
* Existing claim RPCs preserved (`claim_data_setup_session(s)`)

**Limitation documented:** Python fallback for `begin_step` (when RPC missing) is not fully race-free. Production should apply the SQL migration so the RPC path is used. Session-level claim remains primary duplicate protection.

## 11. Remaining limitations

| Item | Reason | Later fix |
|------|--------|-----------|
| No dependency/stale engine | Phase 4 scope | `dependencies.py` / policies |
| No transition authorization | Phase 4 scope | `engine.py` |
| Resume API workflow fields optional | Frontend unused | Phase 8 UX |
| Fallback begin_step not atomic | Migration may lag | Require RPC in prod |
| Mapping coercion still in finalize | Phase 2 boundary | Optional clearer split |

## 12. Test results

```text
pytest tests/test_setup_tools.py tests/test_data_setup.py \
  tests/test_data_setup_worker.py tests/test_etl_execution_compatibility.py \
  tests/test_chat_mapping_gate.py tests/test_etl_pipeline.py \
  tests/test_workflow_steps_migration.py tests/test_workflow_state.py -q
```

```text
passed:  44
failed:  0
skipped: 0
```

## 13. Phase 4 readiness

Ready when instructed:

* Workflow transition checks
* Dependency / skip / stale marking
* Duplicate protection policies beyond begin RPC
* Still **no** AI orchestrator / wizard replacement in Phase 4 MVP

## Before / After

### Phase 2

```text
process_data_setup_session
→ tools execute sequentially
→ state only in process / session blobs
```

### Phase 3

```text
process_data_setup_session
        ↓
read workflow_steps / resume state
        ↓
step running (begin_workflow_step)
        ↓
tool
        ↓
persist ToolResult (+ cleaned artifact for clean)
        ↓
step completed
        ↓
next step

restart / failure
        ↓
load workflow_steps
        ↓
reuse completed boundaries
        ↓
retry failed / incomplete step
```

## Phase 3 exit criteria

* [x] workflow_steps migration exists
* [x] workflow_steps belongs to data_setup_sessions
* [x] step statuses are centralized
* [x] attempt/version semantics are defined
* [x] ToolResult can be persisted safely
* [x] tool execution state is recorded
* [x] failure state is recorded
* [x] completed steps can be detected
* [x] sequencer can resume from supported safe boundaries
* [x] completed cleaning is not blindly rerun (artifact-backed)
* [x] finalize is idempotent against duplicate publish
* [x] ready behavior remains compatible
* [x] wizard/public API remains compatible
* [x] chat gates remain compatible
* [x] RLS/tenant isolation is preserved
* [x] migration tests pass
* [x] relevant Phase 2 tests still pass
* [x] flow.md contains Phase 3 Results

**STOP.** Awaiting instruction before Phase 4.

**Ops note:** apply `backend/supabase/workflow_steps.sql` in Supabase before relying on atomic step claims in production.

---

# Phase 4 Results

**Date:** 2026-08-07  
**Status:** Complete — STOP (do not start Phase 5)  
**Scope:** Workflow Engine as authority for dependencies, transitions, reuse/retry/skip, awaiting_user, stale/invalidation, and superseded history. Compatibility sequencer thinned to engine loop. No AI orchestrator / LLM decisions / wizard replacement / chat tool UX.

## 1. Files added

```text
backend/app/services/workflow/engine.py
backend/app/services/workflow/transitions.py
backend/app/services/workflow/dependencies.py
backend/app/services/workflow/policies.py
backend/app/services/workflow/runners.py
backend/tests/test_workflow_engine.py
```

## 2. Files modified

```text
backend/app/services/workflow/models.py      — WorkflowDecision, WorkflowErrorCode, semantics
backend/app/services/workflow/state.py       — stale / superseded / ready + transition asserts
backend/app/services/workflow/__init__.py    — lazy WorkflowEngine export (import-cycle safe)
backend/app/services/tools/registry.py       — STEP_REGISTRY, resolve_step_type, UnknownStepError
backend/app/services/tools/__init__.py       — lazy TOOL_HANDLERS / finalize imports
backend/app/services/data_setup.py           — process_data_setup_session → engine.run_until_idle
backend/tests/test_setup_tools.py            — registry assertions compatible with STEP_REGISTRY
flow.md                                      — this section
```

No new DB tables. Reuses `workflow_steps` + `data_setup_sessions` only.

## 3. Workflow Engine API

`WorkflowEngine` (`backend/app/services/workflow/engine.py`):

| Method | Role |
|--------|------|
| `get_workflow_plan(session_id)` | Internal plan summary for future UI/AI |
| `get_next_action(session_id)` | Deterministic next `WorkflowDecision` |
| `can_execute_step(session_id, step_type)` | Deps / status / awaiting checks |
| `execute_step(session_id, step_type, …)` | Registry + persistence path |
| `retry_step(session_id, step_type)` | Failed/stale → same or new attempt via `begin_step` |
| `skip_step(session_id, step_type, reason)` | Policy-gated skip with audit reason |
| `mark_awaiting_user(session_id, step_type, reason, context)` | Persist pause |
| `resolve_awaiting_user(session_id, step_type)` | Return step to ready |
| `invalidate_step(session_id, step_type, reason)` | Mark latest completed/skipped stale |
| `invalidate_downstream(session_id, from_step, reason)` | Graph-driven stale propagation |
| `sync_input_validity(session_id, session)` | Fingerprint compare → stale + downstream |
| `run_until_idle(session_id, user_id, …)` | Compatibility loop (`MAX_ENGINE_ACTIONS=20`) |

`WorkflowDecision.action`: `execute` | `reuse` | `retry` | `skip` | `blocked` | `awaiting_user` | `complete`

Stable error codes: `DEPENDENCY_NOT_SATISFIED`, `STEP_ALREADY_RUNNING`, `STEP_AWAITING_USER`, `STEP_NOT_RETRYABLE`, `UNKNOWN_STEP`, `STALE_DEPENDENCY`, `INVALID_TRANSITION`, `ARTIFACT_MISSING`, `SKIP_NOT_ALLOWED`, `MAX_ACTIONS_EXCEEDED`.

## 4. Dependency graph

Logical graph (code truth in `dependencies.py`):

```text
inspect
   ↓
prepare
  ↙   ↘
clean  map
  \    /
   validate
      ↓
   finalize
```

```python
STEP_DEPENDENCIES = {
  "inspect":  set(),
  "prepare":  {"inspect"},
  "map":      {"inspect"},          # prepare not hard-required
  "clean":    {"prepare"},
  "validate": {"prepare", "map"},
  "finalize": {"clean", "validate"},
}
```

**Compatibility planning order** (`SETUP_SEQUENCE`, not dependency truth):

```text
inspect → prepare → map → validate → clean → finalize
```

Temporary note: runtime still prefers this walk so map/validate can finish before clean; both clean and validate must be valid before finalize. Changing order later does not require a schema rewrite.

### Required dependency matrix

| Step | Requires | Can skip | Retryable | Invalidates downstream |
|------|----------|----------|-----------|------------------------|
| inspect | — | No | Yes | prepare, map, clean, validate, finalize |
| prepare | inspect | No | Yes | clean, validate, finalize |
| map | inspect | Policy (explicit) | Yes | validate, finalize *(not clean)* |
| validate | prepare + map | No | Yes | finalize |
| clean | prepare | Policy (explicit) | Yes | finalize |
| finalize | clean + validate (current, non-stale) | No | Yes | — |

## 5. Transition rules

Centralized in `transitions.py` (`assert_transition` before persistence):

| From | Allowed to |
|------|------------|
| pending | ready, running, skipped |
| ready | running, awaiting_user, skipped |
| running | completed, failed, awaiting_user, skipped |
| awaiting_user | ready, running, failed, skipped |
| failed | ready, running, superseded |
| completed | stale, superseded |
| skipped | stale, superseded, ready |
| stale | ready, running, superseded |
| superseded | *(terminal)* |

**Not allowed:** `completed → running` without new attempt/version (via `begin_step` after stale/supersede/fail path).

### Required transition matrix (implemented)

```text
pending → ready
ready → running
running → completed
running → failed
running → awaiting_user
failed → ready
failed → running          # retry attempt via begin_step
completed → stale
stale → ready
stale → running           # new attempt/version
awaiting_user → ready
completed → superseded
```

## 6. Retry policy

* **Execution failure:** same `version`, `attempt + 1` via `begin_workflow_step` / `begin_step`
* **Input/config change:** fingerprint mismatch → mark stale → new version on next execute; history preserved
* Retry verifies deps + (for clean) artifact policy; does **not** restart completed valid upstream steps
* Finalize retry preserves Phase 3 publish idempotency (no duplicate dataset version when already ready/partial)

## 7. Reuse policy

Reuse requires status in `{completed, skipped}` **and** matching input fingerprint (and clean artifact present). Not status-alone.

| Step | Reuse when |
|------|------------|
| inspect | completed + source fingerprint unchanged |
| prepare | completed + source fingerprint unchanged |
| map | completed + mapping fingerprint unchanged |
| validate | completed + mapping + contract fingerprints unchanged |
| clean | completed + profile/source fingerprint + `cleaned_artifact_key` exists |
| finalize | session already `ready` with publish refs, or fingerprint still matches |

Fingerprints are compact hashes in step `input` JSON — no full dataset hashing.

## 8. Skip policy

Conservative (`SKIP_ALLOWED`):

* inspect / prepare / validate / finalize: **never**
* clean / map: only when caller invokes `skip_step` with persisted reason
* Skipped counts as satisfied dependency for finalize when policy allowed
* No heuristic auto-skip of meaningful processing in Phase 4

## 9. Awaiting-user mechanism

* Engine can transition to `awaiting_user` with reason/context on step row
* `get_next_action` returns `action=awaiting_user` and **blocks** downstream
* `process_data_setup_session` maps this to session `awaiting_answers` (no chat UI)
* `resolve_awaiting_user` → ready so a future caller can continue

## 10. Stale / invalidation behavior

* `sync_input_validity` compares stored step input fingerprints to current session
* Mismatch → mark step stale + `invalidate_downstream` via `INVALIDATION_TARGETS`
* Mapping change: validate + finalize stale; **clean remains valid** (finalize re-applies mapping coercion)
* Cleaning profile change: clean stale/new version + finalize stale; map remains valid
* Data contract change: validate + finalize stale
* Source change: inspect fingerprint breaks → cascade via inspect invalidation targets

## 11. Superseded semantics

| Status | Meaning |
|--------|---------|
| **stale** | Result cannot currently be trusted (dependency/input changed) |
| **superseded** | Newer valid logical version replaced this historical result |

Do not treat as interchangeable. Old rows are never deleted.

## 12. process_data_setup_session before / after

### Before (Phase 3)

```text
process_data_setup_session
→ hardcoded sequence + execute_persisted_tool_step per tool
→ manual reuse checks
```

### After (Phase 4)

```text
process_data_setup_session
→ WorkflowEngine.run_until_idle
→ get_next_action (deps / reuse / retry / awaiting_user / stale sync)
→ execute_step → STEP_REGISTRY → runners → tools
→ workflow_steps persistence
→ loop until complete | blocked | awaiting_user
→ finalize-owned session ready (chat gates unchanged)
```

## 13. Tool registry enforcement

* `STEP_REGISTRY` maps canonical step ids → handler + metadata
* `resolve_step_type` / `get_step_entry` fail closed (`UnknownStepError`)
* Engine is the product orchestration path for setup steps
* Lazy registry/tool imports avoid finalize ↔ workflow import cycles

## 14. Remaining bypass paths

| Path | Status |
|------|--------|
| Direct imports of `inspect_source` / `run_clean_data` / etc. | Still importable for tests/legacy; product setup runner uses engine |
| `workflow/runners.py` | Calls tools directly **only** from `engine.execute_step` |
| `get_tool` / `TOOL_HANDLERS` | Legacy Phase 2 access; not used by sequencer |
| Schedule / `execute_etl_recipe` | Separate non-setup ETL path (Phase 2 boundary preserved) |
| Approve / worker | Still call `process_data_setup_session` (now engine-backed) |

Future AI must request steps via `WorkflowEngine.execute_step` / `get_next_action`, not raw tool functions.

## 15. Test results

```text
pytest tests/test_workflow_engine.py tests/test_workflow_state.py \
  tests/test_workflow_steps_migration.py tests/test_setup_tools.py \
  tests/test_data_setup.py tests/test_data_setup_worker.py \
  tests/test_etl_execution_compatibility.py tests/test_chat_mapping_gate.py \
  tests/test_etl_pipeline.py -q
```

```text
passed:  57
failed:  0
skipped: 0
```

Engine suite covers: unknown step, invalid transition, dep blocks, finalize+stale validate, retry without upstream restart, mapping invalidation (clean preserved), skip policy, awaiting_user block/resolve, plan shape.

## 16. Known limitations

| Item | Detail |
|------|--------|
| Confirmation policies | Structure exists; not auto-detected from business content yet |
| Auto-skip heuristics | Intentionally absent |
| Public workflow-plan API | Internal `get_workflow_plan` only; resume may still expose optional metadata |
| Fingerprint on pre-Phase-4 rows | Empty `input` → not reusable until re-executed with fingerprint |
| begin_step Python fallback | Still not fully race-free if RPC missing (Phase 3 note) |
| Confirmation → awaiting_user auto | Engine API present; callers must invoke explicitly |

## 17. Phase 5 readiness

Answered from implemented + tested behavior:

| Question | Answer |
|----------|--------|
| Can a future AI request a tool without bypassing the Workflow Engine? | **Yes** — product path is `execute_step` / `run_until_idle`; document direct imports as non-product |
| Can the engine reject an invalid AI-requested step? | **Yes** — unknown step + dependency/transition failures (tested) |
| Can the engine return `awaiting_user` without running downstream? | **Yes** (tested) |
| Can changing business context invalidate only affected downstream steps? | **Yes** — graph + fingerprints (mapping→validate/finalize, not clean; tested) |
| Can retry occur without restarting completed upstream work? | **Yes** (tested) |
| Can finalization avoid publishing stale results? | **Yes** — finalize blocked on stale/missing clean/validate (tested); Phase 3 publish idempotency preserved |

Phase 5 may add AI Orchestrator **on top of** this engine. Do not let the LLM become the authority for deps/transitions.

## Phase 4 exit criteria

* [x] Workflow Engine exists
* [x] dependency rules centralized
* [x] transition rules centralized
* [x] caller uses engine rather than hardcoded sequencing
* [x] unknown steps fail closed
* [x] invalid dependency execution is blocked
* [x] completed valid steps can be reused
* [x] failed steps can retry without upstream restart
* [x] skip state is controlled and audited
* [x] awaiting_user blocks downstream execution
* [x] stale state is implemented
* [x] downstream invalidation is implemented
* [x] superseded/history semantics are defined
* [x] finalize rejects stale/missing dependencies
* [x] ready state remains finalize-owned
* [x] Tool Registry is enforced by engine
* [x] Phase 2/3 compatibility remains intact
* [x] relevant tests pass (57)
* [x] flow.md contains Phase 4 Results

**STOP.** Do not start Phase 5 (AI Orchestrator / LLM tool calling / chat-driven ETL questions / wizard replacement / tool cards).

---

# Phase 4.5 Pre-AI Hardening Results

**Date:** 2026-08-07  
**Status:** Complete — STOP (do not start Phase 5)  
**Scope:** Pre-AI hardening of Workflow Engine authority — confirmation gates, fingerprint-bound approvals, production RPC fail-closed, stable WorkflowPlan + AI-safe context. No LLM / orchestrator / wizard replacement.

## 1. Files added

```text
backend/app/services/workflow/capability.py
backend/app/services/workflow/orchestrator_context.py
backend/supabase/workflow_begin_step_ready.sql
backend/tests/test_workflow_hardening.py
```

## 2. Files modified

```text
backend/app/core/config.py                 — APP_ENV, WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK
backend/app/main.py                        — startup workflow capability check
backend/app/worker.py                      — worker startup capability check
backend/app/services/workflow/engine.py    — confirmation, plan, resolve, reuse harden
backend/app/services/workflow/policies.py  — evaluate_confirmation_requirement + fingerprints
backend/app/services/workflow/models.py    — ConfirmationDecision, WorkflowPlan*
backend/app/services/workflow/state.py     — production RPC fail-closed; ready reclaim
backend/app/services/workflow/transitions.py — awaiting_user/ready → stale
backend/app/services/workflow/__init__.py  — exports
backend/app/services/workflow/runners.py   — engine-only docstring
backend/app/services/tools/registry.py     — STEP_REGISTRY canonical; legacy deprecated
backend/app/services/tools/__init__.py     — lazy legacy accessors
backend/app/services/data_setup.py         — awaiting_answers pause; engine-only runner
backend/app/services/etl_execution.py      — schedule/manual vs setup boundary docs
backend/supabase/README.md                 — migration 28
backend/tests/test_setup_tools.py
backend/tests/test_workflow_engine.py
flow.md                                    — this section
```

## 3. Raw tool call audit

| Call site | Calls | Classification | Allowed after hardening? |
|-----------|-------|----------------|--------------------------|
| `workflow/runners.py` | inspect/prepare/map/validate/clean/finalize tools | internal runner (engine-owned) | Yes |
| `workflow/engine.py` → runners | step execution | product setup runtime | Yes (via engine) |
| `data_setup.process_data_setup_session` | `WorkflowEngine.run_until_idle` only | product setup runtime | Yes |
| `data_setup_worker` / approve route | `process_data_setup_session` | product setup runtime | Yes |
| `tools/*.py` definitions | self | tool implementations | Yes |
| `tests/test_setup_tools.py` | raw tools | test-only | Yes |
| `tests/test_workflow_state.py` | `finalize_data_setup` | test-only | Yes |
| `tools/registry.py` `TOOL_HANDLERS` / `get_tool` | legacy view | legacy compatibility | Yes (deprecated; not orchestration) |
| `etl_execution.execute_etl_recipe` | schedule/manual recipe path | scheduled/manual ETL | Yes (not setup workflow) |
| `etl_scheduler` / manual run route | `execute_etl_recipe` | scheduled/manual ETL | Yes |
| `data_setup.preview_setup_rows` | `clean_dataframe` | wizard preview (not workflow step) | Yes (preview only) |
| `dataset_engine` / `data_cleaning` | shared clean helpers | shared library | Yes |

**Product data-setup execution path is engine-only.** No normal product setup path invokes raw setup tools directly.

## 4. Canonical registry decision

* **`STEP_REGISTRY`** = authoritative workflow registry (step_type → handler/metadata)
* **`TOOL_HANDLERS` / `get_tool`** = deprecated compatibility views over the same imports
* DeprecationWarning on legacy access; new orchestration must use `WorkflowEngine`

## 5. Confirmation policy implementation

`evaluate_confirmation_requirement(session, step_type, proposed_input=..., workflow_plan=...)`
→ `ConfirmationDecision(required, reason_code, reason, context, confirmation_fingerprint)`

### Required confirmation matrix

| Situation | Confirmation required | Reason code | Auto-detected? |
|-----------|-----------------------|-------------|----------------|
| standard / financial / conservative clean | No | — | Yes |
| aggressive clean | Yes | `AGGRESSIVE_CLEANING` | Yes |
| mapping with `require_mapping_confirmation` / `mapping_flags.ambiguous` | Yes | `AMBIGUOUS_MAPPING` | Mechanism only (explicit flag) |
| validate with `require_contract_confirmation` / contract.requires_confirmation | Yes | `BUSINESS_CONTRACT_CHANGE` | Mechanism only (explicit flag) |
| destructive / semantic meaning | Policy keys exist | `DESTRUCTIVE_TRANSFORM` / `SEMANTIC_MEANING_REQUIRED` | Not auto-detected yet |

## 6. awaiting_user integration

* `execute_step` evaluates confirmation **before** tool runner
* If required and no matching approval → persist `awaiting_user`, raise `ConfirmationRequired`, **tool not invoked**
* `run_until_idle` / `get_next_action` return `awaiting_user` and stop
* `process_data_setup_session` maps to session `awaiting_answers` and will not clobber pause on re-entry
* Worker only claims `approved` sessions → cannot accidentally continue `awaiting_answers`

## 7. Confirmation resolution semantics

```python
resolve_awaiting_user(session_id, step_type, resolution={
  "decision": "approved" | "rejected" | "modified",
  "context_updates": {...}
})
```

* **approved / modified** → step `ready` + audited resolution metadata; execute may proceed if fingerprint still matches
* **rejected** → step `failed` (`CONFIRMATION_REJECTED`); operation does not execute; engine blocked/replan
* Resolution persisted under `output.metadata.resolution`

## 8. Confirmation fingerprint behavior

* `confirmation_fingerprint` = hash of `{step_type, reason_code, proposed_input}` (no datasets)
* Bound on awaiting_user input; required for approve → execute
* Input/profile change → `sync_input_validity` marks awaiting_user **stale**; old confirmation cannot authorize new action
* `ready` reclaim via `begin_step` preserves confirmation fingerprint (SQL + Python fallback)

## 9. Production atomic-step policy

* `APP_ENV=production|prod` → `begin_workflow_step` RPC **required** (fail closed)
* `WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK` explicit override for tests/dev
* Python fallback remains for non-production only
* Startup/worker: `ensure_workflow_persistence_ready` (table + RPC probe in production)
* Additive SQL: `workflow_begin_step_ready.sql` (migration 28) — reclaim `ready` rows in place

## 10. Legacy fingerprint behavior

* Missing input fingerprint ⇒ **not reusable** (safe rerun / new version)
* Status=`completed` alone never authorizes reuse
* Covered by `test_missing_fingerprint_not_reusable`

## 11. WorkflowPlan contract

`WorkflowPlan` / `WorkflowPlanStep` models + `get_workflow_plan(..., as_model=True)`

Fields: `session_id`, `status`, `current_step`, `next_action`, `steps[]` (status/version/attempt/reusable/retryable/requires_confirmation/stale_reason/latest_summary), `blockers`, `awaiting_user`, `last_failed_step`

Compact — no full ToolResult payloads.

## 12. AI-safe context contract

`build_orchestrator_workflow_context(plan)` / `WorkflowEngine.to_orchestrator_context(...)`

* Strips password/token/secret/service_role/signed_url/traceback/raw_dataframe/api_key/…
* Bounded (~8k chars)
* **No LLM calls**

## 13. Schedule / manual ETL boundary

```text
Data Setup workflow     → WorkflowEngine
Scheduled/manual ETL    → execute_etl_recipe (legacy)
```

Phase 5 AI Orchestrator must **not** use `execute_etl_recipe` to bypass setup workflow rules.

## 14. Remaining bypass paths

| Path | Notes |
|------|-------|
| Direct tool imports | Tests / library use only |
| `TOOL_HANDLERS` / `get_tool` | Deprecated; not product authority |
| `execute_etl_recipe` | Explicit non-setup boundary |
| Wizard `preview_setup_rows` | Preview path; does not advance workflow_steps |

## 15. Test results

```text
pytest tests/test_workflow_hardening.py tests/test_workflow_engine.py \
  tests/test_workflow_state.py tests/test_workflow_steps_migration.py \
  tests/test_setup_tools.py tests/test_data_setup.py \
  tests/test_data_setup_worker.py tests/test_etl_execution_compatibility.py \
  tests/test_chat_mapping_gate.py tests/test_etl_pipeline.py -q
```

```text
passed:  70
failed:  0
skipped: 0
```

## 16. Known limitations

| Item | Detail |
|------|--------|
| Ambiguous mapping / contract change | Require explicit session flags; not heuristic auto-detect |
| Auto-skip | Still intentionally absent |
| `workflow_begin_step_ready.sql` | Must be applied on Supabase for production ready-reclaim semantics |
| Confirmation UX | Backend only; no chat/wizard UI yet |
| Schedule ETL unification | Out of scope |

## 17. Phase 5 readiness

| # | Question | Answer |
|---|----------|--------|
| 1 | Can an AI obtain a compact workflow plan without raw data? | **Yes** — `to_orchestrator_context` (tested) |
| 2 | Can an AI request only canonical step IDs? | **Yes** — `resolve_step_type` / `STEP_REGISTRY` |
| 3 | Can an invalid step be rejected before tool execution? | **Yes** (Phase 4 + 4.5 tests) |
| 4 | Can confirmation-sensitive execution pause without LLM authority? | **Yes** — aggressive clean → awaiting_user (tested) |
| 5 | Can user confirmation be tied to the exact proposed input? | **Yes** — confirmation_fingerprint (tested) |
| 6 | Can a worker accidentally continue while awaiting_user? | **No** — claim filter + engine pause + session status guard (tested) |
| 7 | Can production silently fall back to a race-prone step claim? | **No** — fail closed (tested) |
| 8 | Can AI bypass setup workflow through execute_etl_recipe? | **Must not** — documented boundary; not a setup API |
| 9 | Are remaining direct tool imports non-product/test/legacy only? | **Yes** (audit table) |
| 10 | Ready for structured ask_user/tool_call/respond decisions? | **Yes for engine substrate** — Phase 5 may add orchestrator on top |

## Phase 4.5 exit criteria

* [x] product setup execution remains engine-only
* [x] STEP_REGISTRY is canonical
* [x] legacy registry access cannot become a second authority
* [x] deterministic confirmation evaluation exists
* [x] confirmation requirement produces awaiting_user before execution
* [x] confirmation resolution is explicit and audited
* [x] confirmation is input/fingerprint-bound
* [x] input changes invalidate pending confirmation
* [x] awaiting_user blocks worker/run_until_idle continuation
* [x] production requires atomic DB step claim or fails closed
* [x] old missing fingerprints are handled safely
* [x] stable WorkflowPlan model exists
* [x] AI-safe workflow context exists without LLM
* [x] schedule/manual ETL boundary is documented
* [x] relevant tests pass (70)
* [x] Phase 2/3/4 behavior remains compatible
* [x] flow.md contains hardening results

**STOP.** Do not start Phase 5.

**Ops note:** apply `backend/supabase/workflow_begin_step_ready.sql` on Supabase (after `workflow_steps.sql`) so production reclaim of approved `ready` steps matches the Python fallback behavior.

---

# Phase 5 AI Orchestrator Results

**Date:** 2026-08-08  
**Status:** Complete — STOP (do not remove wizard / do not start next phase)  
**Scope:** Conversational AI Orchestrator on top of WorkflowEngine. LLM proposes structured decisions; engine remains authority. Wizard coexistence + feature flag.

## Production capability check

Verified on Supabase project `Analyst_app` (`pamqpagnddorxktamqdk`):

* `begin_workflow_step` RPC present
* Phase 4.5 `ready` reclaim path present (`latest.status = 'ready'`)
* Production fail-closed policy unchanged (`WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK` / `APP_ENV`)

## 1. Files added

```text
backend/app/services/orchestrator/__init__.py
backend/app/services/orchestrator/orchestrator.py
backend/app/services/orchestrator/context_builder.py
backend/app/services/orchestrator/decision_models.py
backend/app/services/orchestrator/decision_parser.py
backend/app/services/orchestrator/decision_validator.py
backend/app/services/orchestrator/prompts.py
backend/app/services/orchestrator/resolution.py
backend/app/services/orchestrator/session_updates.py
backend/tests/test_orchestrator.py
backend/tests/test_orchestrator_decisions.py
backend/tests/test_chat_orchestrator_integration.py
```

## 2. Files modified

```text
backend/app/core/config.py          — ENABLE_CONVERSATIONAL_DATA_SETUP, LLM_MODEL_ORCHESTRATOR, MAX_ORCHESTRATOR_ACTIONS
backend/app/api/routes.py           — setup routing before ready/mapping gates
backend/app/schemas/chat.py         — optional ChatResponse.orchestration
backend/.env.example                — flag + orchestrator model knobs
flow.md                             — this section
```

## 3. Existing LLM infrastructure reused

| Component | Reuse |
|-----------|--------|
| `LlmClient.safe_chat_completion` | Structured decision calls (non-stream) |
| OpenRouter headers / provider routing | Via existing `LlmClient` |
| 429 → fallback model | Inherited |
| `CHAT_REQUEST_TIMEOUT_SECONDS` | Global middleware |
| No second LLM client stack | Confirmed |

Avoided: sync `insight.py` / `schema_ai.py` clients.

## 4. Orchestrator architecture

```text
User
 ↓
Chat (/chat, /chat/stream)
 ↓
Setup routing (flag + non-ready session)
 ↓
AI Orchestrator
 ↓
WorkflowPlan + safe context (Phase 4.5)
 ↓
Structured Decision (ask_user | tool_call | respond)
 ↓
Decision Validator
 ↓
WorkflowEngine (execute_step / resolve_awaiting_user / get_workflow_plan)
 ↓
STEP_REGISTRY → runners → tools
 ↓
workflow_steps
 ↓
updated WorkflowPlan
 ↓
Assistant response (grounded in engine result)
```

## 5. Decision schemas

* `ask_user` — question, reason, context_key, options[]
* `tool_call` — canonical `step_type`, reason, proposed_input{}
* `respond` — message

Unknown types / forbidden fields (`sql`, `shell`, `execute_etl_recipe`, secrets) fail closed.

## 6. Decision validation

Pre-engine checks only:

* canonical step via `resolve_step_type` / `STEP_REGISTRY`
* session exists
* proposed_input shape/size/forbidden keys
* ask_user options bounded

Dependency/confirmation/stale remain in WorkflowEngine.

## 7. Workflow context contract

Uses `build_orchestrator_llm_context` → `WorkflowEngine` plan + `build_orchestrator_workflow_context` + compact scan/contract summaries + recent turns (bounded). No DataFrames, credentials, raw ToolResult dumps.

## 8. System prompt / version

* `MATAQOR_ORCHESTRATOR_PROMPT_VERSION = "1.0"`
* Centralized in `orchestrator/prompts.py`
* Deterministic templates for confirmation reason codes

## 9. Tool-call flow

```text
validate → engine.execute_step → reload plan → assistant from actual result
```

`ConfirmationRequired` → `ask_user` (template), tool not executed. Max one step per decision; loop cap `MAX_ORCHESTRATOR_ACTIONS` (default 3).

## 10. awaiting_user flow

Backend reason_code → template question (+ options) → chat response. LLM may personalize only when not in confirmation pause; confirmation pause prefers deterministic templates / user resolution parsing.

## 11. User resolution parsing

Deterministic phrases (Thai/English): approved / rejected / modified (e.g. profile change) / ambiguous. Ambiguous → re-ask (never silent approve). Then `WorkflowEngine.resolve_awaiting_user`.

## 12. Data Contract / mapping update boundaries

`session_updates.apply_context_updates` allowlist:

* `cleaning_profile` ∈ {standard, financial, conservative, aggressive}
* `return_policy` (user_confirmed) via `normalize_data_contract` when possible
* `column_mapping` shallow merge of valid column→role pairs

No arbitrary contract JSON from the LLM.

## 13. Chat integration

When `ENABLE_CONVERSATIONAL_DATA_SETUP` and session status ≠ `ready`:

* `/chat` and `/chat/stream` route to orchestrator **before** mapping/ready gates
* Ready sessions keep existing analysis chat path + gates unchanged

Stream emits `status` / `token` / `done` (+ `orchestration` payload).

## 14. Feature flag

```text
ENABLE_CONVERSATIONAL_DATA_SETUP=false   # default
LLM_MODEL_ORCHESTRATOR=                 # optional
MAX_ORCHESTRATOR_ACTIONS=3
```

## 15. LLM failure behavior

Timeout / provider / malformed JSON → one repair attempt → deterministic fallback from `WorkflowPlan.next_action` / awaiting templates. Workflow state not mutated by invalid model output.

## 16. Audit / logging

`OrchestratorResult.audit` + structured logs: session_id, decision_type, step, reason, prompt_version. No credentials/full prompts/datasets.

## 17. Loop / token controls

* `MAX_ORCHESTRATOR_ACTIONS`
* repeated identical tool request guard
* bounded workflow context (~8k safe builder) + truncated turns/tool summaries

## 18. Remaining wizard behavior

`DataSetupCopilot` and `/data-setup/*` unchanged. Wizard and orchestrator share WorkflowEngine fingerprints/invalidation.

## 19. Test results

```text
pytest tests/test_orchestrator*.py tests/test_chat_orchestrator_integration.py \
  tests/test_workflow_*.py tests/test_setup_tools.py tests/test_data_setup*.py \
  tests/test_etl_*.py tests/test_chat_mapping_gate.py -q
```

```text
passed:  90
failed:  0
```

## 20. Known limitations

| Item | Detail |
|------|--------|
| Flag default off | Staged rollout |
| Heuristic business questions | Limited (return_policy / flags); not open-ended autonomy |
| Mapping AI proposals | Allowlisted updates only; no full AI remapping |
| Stream UX | Text response as single token chunk (no token streaming of LLM decision) |
| Wizard UI for ask_user options | Payload ready; Phase 8 UI cards not built |

## 21. Phase 6 readiness

Ready for later frontend conversational polish / tool cards **on top of** this orchestrator — not required to remove the wizard.

### Required decision matrix

| AI decision | Backend behavior |
|-------------|------------------|
| ask_user | Return question/options only; no tool execution |
| tool_call | validate → WorkflowEngine.execute_step |
| respond | User-facing message only |
| awaiting_user resolution | parse → resolve_awaiting_user → optional execute |

### Required security / authority check

| # | Question | Answer |
|---|----------|--------|
| 1 | Can the LLM call raw tools directly? | **No** |
| 2 | Can the LLM call execute_etl_recipe? | **No** |
| 3 | Can the LLM bypass dependency checks? | **No** (engine rejects; tested) |
| 4 | Can the LLM bypass confirmation requirements? | **No** (awaiting_user; tested) |
| 5 | Can malformed LLM output execute anything? | **No** (fail closed; tested) |
| 6 | Can LLM text mark a step completed? | **No** (grounded in engine/ToolResult; tested) |
| 7 | Does WorkflowEngine remain authoritative? | **Yes** |
| 8 | Are workflow/source contexts sanitized before LLM use? | **Yes** (Phase 4.5 builder) |

## Phase 5 exit criteria

* [x] AI Orchestrator exists
* [x] existing LLM infrastructure reused
* [x] structured ask_user/tool_call/respond schemas
* [x] malformed decisions fail closed
* [x] canonical step IDs only
* [x] tool_call routes through WorkflowEngine
* [x] LLM cannot bypass confirmations
* [x] awaiting_user → conversational question
* [x] structured confirmation resolution
* [x] ambiguous resolution does not auto-approve
* [x] workflow plan reloaded after tool execution
* [x] user-facing success from backend state
* [x] context bounded/sanitized
* [x] loop guard exists
* [x] feature flag exists
* [x] wizard remains functional
* [x] ready sessions use analysis chat path
* [x] LLM failures do not corrupt workflow state
* [x] previous tests remain green
* [x] new orchestrator tests pass
* [x] flow.md contains Phase 5 Results

**STOP.** Do not remove/replace the wizard. Do not start the next phase (tool cards / large frontend redesign / multi-agent autonomy).

# Phase 6 Conversational UX Bridge Results

Phase 6 turns Phase 5 orchestration payloads into a guided chat data-preparation UX. WorkflowEngine remains authoritative; the frontend never infers progress from assistant prose and never calls tools/workflow DB directly.

## 1. Files added

| Path | Purpose |
|------|---------|
| `backend/app/services/orchestrator/ui_payload.py` | Safe UI orchestration payload builder |
| `backend/tests/test_orchestrator_ui_payload.py` | Payload contract tests |
| `backend/tests/test_chat_orchestration_resolution.py` | ChatRequest resolution field |
| `src/features/chat/orchestration/labels.js` | Step/status labels (TH/EN) |
| `src/features/chat/orchestration/normalize.js` | FE normalization + send contracts |
| `src/features/chat/orchestration/WorkflowProgress.tsx` | Compact progress / source header |
| `src/features/chat/orchestration/WorkflowQuestionCard.tsx` | ask_user / confirmation options |
| `src/features/chat/orchestration/ToolResultCard.tsx` | Safe tool summaries |
| `src/features/chat/orchestration/WorkflowErrorCard.tsx` | Failure + retry |
| `src/features/chat/orchestration/ReadyForAnalysisCard.tsx` | Ready transition + assurance layers |
| `src/features/chat/orchestration/OrchestrationMessage.tsx` | Message-level composition |
| `src/features/chat/orchestration/index.js` | Public exports + local flag hint |
| `src/features/chat/orchestration/normalize.test.js` | Progress/options/retry contract tests |
| `src/features/chat/orchestration/components.test.js` | Component render tests |

## 2. Files modified

| Path | Change |
|------|--------|
| `backend/app/schemas/chat.py` | `orchestration_resolution` on ChatRequest |
| `backend/app/api/routes.py` | UI payload; structured resolution; `GET /capabilities` |
| `backend/app/services/orchestrator/orchestrator.py` | Structured resolution + UI retry action |
| `src/features/chat/chatStream.js` | Persist `orchestration` from SSE `done` |
| `src/features/chat/chatStream.test.js` | SSE orchestration survival test |
| `src/features/chat/hooks/useChatSend.js` | Attach orchestration; setup pause path; resolution field |
| `src/features/chat/ChatMessageList.tsx` | Render OrchestrationMessage |
| `src/views/Chat.tsx` | Flag fetch, wizard coexistence, resolve/ready handlers |
| `.env.example` | Optional `NEXT_PUBLIC_ENABLE_CONVERSATIONAL_DATA_SETUP` |
| `flow.md` | This Phase 6 Results section |

## 3. Frontend orchestration types

Normalized view (from backend payload; no invented fields):

```ts
type WorkflowStepStatus =
  | "pending" | "ready" | "running" | "awaiting_user"
  | "completed" | "failed" | "skipped" | "stale" | "superseded";

interface WorkflowStepView {
  stepType: string;
  label: string;
  status: WorkflowStepStatus;
  version?: number;
  attempt?: number;
  summary?: string | null;
  retryable?: boolean;
}

interface OrchestrationPayload {
  decisionType?: "ask_user" | "tool_call" | "respond";
  workflow?: WorkflowProgress;
  awaitingUser?: AwaitingUserPayload;
  toolResult?: ToolResultView;
  source?: SourceSummary;
  assurance?: AssuranceSummary;
  readyForAnalysis?: boolean;
  options?: OptionView[];
  errorKind?: "tool_failure" | "orchestrator_failure" | "awaiting_user" | null;
}
```

Implemented via `normalizeOrchestration()` in `normalize.js` (project tests are JS/vitest).

## 4. Workflow progress UI

`WorkflowProgress` renders backend `orchestration.workflow` / WorkflowPlan steps only:

* Desktop/tablet: vertical compact checklist (`✓ / ● / ◉ / ! / ↻ / ○`)
* Mobile: `completed / total · active label` + expandable step list
* Source header: name · rows · columns (safe metadata only)
* Stale shown as “ต้องตรวจสอบใหม่” (not raw version IDs)
* `superseded` filtered from compact bar

## 5. Ask-user / confirmation UI

`WorkflowQuestionCard` binds to `awaiting_user` + structured `options`.

* Confirmation reasons (`AGGRESSIVE_CLEANING`, etc.) use stronger card styling
* Buttons disabled while request in flight / parent `isGenerating`
* Historical messages keep question text but omit actionable buttons when setup is inactive

## 6. Tool result cards

`ToolResultCard` uses `orchestration.tool_result` (safe summary/findings/warnings/metadata).

Missing optional fields do not crash. Details are progressive (`View details`).

## 7. Error / retry UX

`WorkflowErrorCard` differentiates tool failure vs orchestrator failure copy.

Retry appears only when `retryable === true` and sends:

```json
{ "action": "retry", "step_type": "<step>" }
```

through Chat → Orchestrator → WorkflowEngine (never raw tool endpoints).

## 8. Ready-for-analysis UX

`ReadyForAnalysisCard` shows when `ready_for_analysis` / session ready.

Assurance layers remain separate:

* Computation readiness
* Data readiness
* Business context

On ready, Chat refreshes session via `GET /data-setup/{id}` and promotes analysis context (`handleDataSetupReady`). Setup controls deactivate; historical cards remain.

## 9. Wizard coexistence

`DataSetupCopilot` remains.

When conversational flag is on:

* Chat is preferred lightweight path
* “ตั้งค่าแบบละเอียด” expands the existing wizard
* Flag off → previous wizard-first behavior unchanged

## 10. SSE integration

`consumeChatStream` now keeps `result.orchestration` from `done` (and optional `orchestration` events).

`useChatSend` attaches `orchestration` onto the final AI message (including `agent_paused` setup path) so payloads survive streaming state updates.

## 11. Feature flag behavior

| Flag | Behavior |
|------|----------|
| `ENABLE_CONVERSATIONAL_DATA_SETUP=false` | Wizard path; no conversational setup UI preference |
| `ENABLE_CONVERSATIONAL_DATA_SETUP=true` | Conversational UX enabled; wizard still available |
| FE | `GET /api/v1/capabilities` authoritative; optional `NEXT_PUBLIC_ENABLE_CONVERSATIONAL_DATA_SETUP` hint only |

## 12. Backend payload additions

`build_orchestration_ui_payload()` adds:

* `workflow` (normalized step list + ready flag)
* `tool_result` (bounded, path/secret keys stripped)
* `source` / `assurance`
* `ready_for_analysis`

Keeps `workflow_plan` / `engine_result` for backward compatibility.

Also:

* `ChatRequest.orchestration_resolution`
* Orchestrator structured approve/reject/modified + `action: retry`
* `GET /api/v1/capabilities`

## 13. Accessibility / responsive behavior

* Status communicated with glyphs **and** sr-only / text labels (not color alone)
* Option/retry buttons: semantic `<button>`, focus-visible rings, `aria-busy` / `aria-expanded`
* Mobile progress collapses to compact summary

## 14. Test results

Frontend (vitest):

```text
src/features/chat/orchestration/normalize.test.js     10 passed
src/features/chat/orchestration/components.test.js      8 passed
src/features/chat/chatStream.test.js                    8 passed
Total                                                  26 passed
```

Backend (related Phase 5/6 + gates):

```text
orchestrator + workflow + setup tools + ui payload
+ chat mapping gate + data_setup + etl compatibility
→ 79 passed
```

## 15. Known limitations

* No fake percentage progress (backend does not emit %)
* No full mapping spreadsheet editor in chat (wizard remains)
* Wizard→chat sync relies on next orchestrator turn / ready refresh (no separate FE workflow store)
* Assistant narrative dedupe only when content equals awaiting question text
* Local FE flag alone cannot enable backend routing

## 16. Phase 7 readiness

Phase 6 exit criteria met for conversational UX bridge. Later phases may deepen analytics/agent work — **without** removing the wizard or increasing AI authority over WorkflowEngine.

### Required Component Matrix

| Component | Purpose | Backend source |
|-----------|---------|----------------|
| WorkflowProgress | step progress | `orchestration.workflow` / WorkflowPlan |
| WorkflowQuestionCard | ask_user | `orchestration.awaiting_user` + options |
| ToolResultCard | completed tool summary | `orchestration.tool_result` |
| WorkflowErrorCard | failure/retry | workflow/tool failed + retryable |
| ReadyForAnalysisCard | setup complete | `ready_for_analysis` + assurance |

### Required User Action Matrix

| User action | Frontend | Backend path |
|-------------|----------|--------------|
| Approve | option button | Chat → Orchestrator → `resolve_awaiting_user` |
| Modify | option button | Chat → Orchestrator → session update → engine |
| Reject | option button | Chat → Orchestrator → resolve reject |
| Retry | retry button | Chat + `action:retry` → Orchestrator → WorkflowEngine |
| Open advanced setup | “ตั้งค่าแบบละเอียด” | existing `DataSetupCopilot` |

## Phase 6 exit criteria

* [x] conversational setup progress is visible
* [x] progress uses backend WorkflowPlan state
* [x] ask_user options render as structured controls
* [x] confirmation options cannot double-submit
* [x] tool summaries render from safe structured result
* [x] failed retryable steps have safe retry UX
* [x] awaiting_user visually blocks continuation
* [x] ready transition is clear
* [x] assurance layers remain separate
* [x] wizard remains available
* [x] feature flag behavior remains correct
* [x] ready sessions use normal analysis chat
* [x] SSE orchestration payload survives correctly
* [x] frontend never directly executes tools/workflow DB
* [x] responsive behavior is acceptable
* [x] accessibility basics are implemented
* [x] frontend tests pass
* [x] backend Phase 5 tests remain green
* [x] flow.md contains Phase 6 Results

**STOP.** Do not remove the wizard. Do not start wizard replacement, multi-agent autonomy, scheduled-report orchestration, or dashboard redesign.

# Phase 7 End-to-End Validation & Observability Results

Phase 7 proves Phases 1–6 work together under CI-safe scenario tests, adds structured workflow observability, and classifies rollout readiness. No new AI autonomy. Wizard retained.

## 1. Test coverage audit

| Area | Status | Notes |
|------|--------|-------|
| File source | **Covered** | Unit tools + new E2E-01 |
| REST API source (workflow) | **Partial** | E2E-11 mocked runners/`source_type=api`; no live HTTP prepare |
| Database/SQL source (workflow) | **Partial** | E2E-12 mocked `source_type=sql`; no live SQL provider |
| Conversational setup / orchestrator | **Covered** | Phase 5 + E2E deterministic overrides |
| awaiting_user / confirmation | **Covered** | Hardening + E2E-02 |
| Retry | **Covered** | E2E-05 attempt history |
| Backend restart / resume | **Covered** | E2E-06 new engine + artifact reuse |
| Ready → analysis handoff | **Covered** | E2E-09 routing gate |
| Feature flag | **Covered** | E2E-10 + `/capabilities` |
| Stale / invalidation | **Covered** | Engine + E2E-08 / profile change |
| Duplicate dispatch | **Partial** | E2E-07 finalize idempotency; not live concurrent RPC race |
| workflow_steps persistence | **Covered** | Fake client + migration lint; live RPC reclaim = manual/ops |

## 2. E2E scenarios

Canonical list: `backend/tests/fixtures/workflow/SCENARIOS.md` (E2E-01 … E2E-12).

## 3. Fixtures created

Synthetic only (no confidential data):

| File | Purpose |
|------|---------|
| `backend/tests/fixtures/workflow/sales_clean.csv` | Simple clean sales |
| `backend/tests/fixtures/workflow/sales_dirty.csv` | Dupes / mixed dates / negatives |
| `backend/tests/fixtures/workflow/sales_returns.csv` | Return-policy negatives |
| `backend/tests/fixtures/workflow/sales_mapping_ambiguous.csv` | `PRICE_LEVEL` ambiguity |
| `backend/tests/fixtures/workflow/SCENARIOS.md` | Scenario catalog |
| `docs/conversational_setup_smoke.md` | Manual smoke checklist |

## 4. File-source validation

Automated via `tests/e2e/test_conversational_setup_file.py`:

* inspect→prepare→map→validate→clean→finalize→ready
* workflow history assertions (`v1 attempt1 completed`)
* deterministic orchestrator overrides exercise parser/validator/engine path (no external LLM)

## 5. API-source validation

Automated **mocked** path (`source_type=api`) through engine runners — **Pass (mocked)**.  
Real REST pagination/schema stability remains **manual** (see smoke checklist).

## 6. Database-source validation

Automated **mocked** path (`source_type=sql`) via `run_until_idle` — **Pass (mocked)**.  
Real SQL provider remain **manual**.

## 7. Confirmation validation

E2E-02: aggressive clean → `awaiting_user` (tool not completed) → Standard modify → `CONFIRMATION_STALE` → replan → clean completes. History preserved (≥2 clean rows).

## 8. Retry validation

E2E-05: forced clean failure → upstream stays completed → `retry_step` → completed → finalize → ready. Failed + completed history retained.

## 9. Resume validation

E2E-06: seed through clean → new `WorkflowEngine` → clean reused (artifact present) → finalize only.  
E2E artifact-missing: completed clean without artifact → stale/`ARTIFACT_MISSING` path → safe re-exec.

## 10. Ready→analysis validation

E2E-09/10: `status=ready` never routes to orchestrator; flag false blocks conversational routing; flag true routes non-ready; `/capabilities` mirrors flag.

## 11. Workflow event model

`backend/app/services/workflow/events.py`:

* `WorkflowEvent` + `emit_workflow_event` / `timed_step`
* Events: started/completed/failed/retried/reused/awaiting_user/resolved/stale/ready/blocked + orchestrator decision/fallback/rejection/llm_failed/malformed
* Sensitive metadata keys stripped; optional in-process sinks for tests

## 12. Structured logging

Engine/orchestrator emit structured extras: `session_id`, `step_type`, `version`, `attempt`, `duration_ms`, `reason_code`, `source_type`, `decision_type`. No datasets/credentials/prompts.

## 13. Timing metrics

* Per-step `duration_ms` via `timed_step` around tool execution
* Session `total_elapsed_ms` / `awaiting_user_ms` / `processing_ms` in `summarize_session_observability`
* Config: `WORKFLOW_RUNNING_STUCK_MINUTES` (default 120), `WORKFLOW_AWAITING_USER_STALE_HOURS` (default 24)

## 14. Orchestrator metrics

Process counters: `decision:*`, `event:orchestrator_fallback`, `event:orchestrator_malformed_decision`, `event:orchestrator_engine_rejection`, `awaiting_user_questions`.

## 15. Stuck-workflow detection

`find_stuck_workflows(...)` — diagnostic only (no auto mutation):

* running beyond threshold
* awaiting_user beyond threshold
* approved/`ready` step idle
* failed session

## 16. Workflow health summary

`GET /api/v1/ops/workflow-health` (org owner/admin only, audited):

* counts ready/failed/awaiting/running
* median setup ms
* step failures/retries
* stuck samples
* process counters
* scoped by `user_id` (default caller) — no unauthenticated public exposure

## 17. Failure recovery matrix

| Failure | Expected state | Auto recover? | User action | Data loss risk |
|---------|----------------|---------------|-------------|----------------|
| LLM timeout | workflow unchanged | deterministic fallback | none | none |
| Malformed LLM output | reject → fallback | yes (fail closed) | none | none |
| Tool failure | step failed, upstream kept | retryable | Retry | none |
| Clean artifact missing | reuse rejected / stale | replan + re-exec | none/retry | none |
| Worker/backend restart | resume from workflow_steps | reuse completed + artifacts | none | none |
| Duplicate finalize | idempotent reuse | yes | none | none |
| Confirmation rejection | step failed | no | re-request/other path | none |
| Confirmation modify (profile) | confirmation stale → replan | yes | choose option | none |
| Stale dependency | downstream stale | replan affected steps | continue chat | none |
| Finalize failure | finalize failed | retry | Retry | none |

## 18. Security regression results

* UI payload / event metadata strip paths/tokens
* Ops health requires org admin + audit log
* Session scope defaults to caller `user_id`
* Phase 5 authority tests remain green (no raw-tool bypass)
* Concrete defect fixed: `return_policy` user_confirmed provenance preserved after `normalize_data_contract`

## 19. Test results

Frontend (vitest orchestration/stream): **26 passed**

Backend (Phase 5/6/7 core + E2E + observability): **85 passed**

## 20. Manual smoke test results

Checklist authored: `docs/conversational_setup_smoke.md`.  
**Not executed in this Phase 7 automation run** (no live Supabase/LLM smoke claimed).

## 21. Known limitations

* API/SQL E2E use mocked tool runners (not live ingest/pagination)
* Concurrent BackgroundTask+worker RPC race not live-tested in CI
* `workflow_begin_step_ready` reclaim window still SQL-level (2h) + Python stuck thresholds for diagnostics
* No Prometheus/Grafana/OTel added (by design)
* Manual smoke / internal rollout still required before broader enablement

## 22. Rollout readiness

### Classification: **INTERNAL ONLY**

Evidence for controlled internal enablement:

* Critical file/confirm/retry/resume/ready/flag E2E automated and green
* Observability + stuck detection + ops health summary available
* Kill switch `ENABLE_CONVERSATIONAL_DATA_SETUP` remains default **false**
* Wizard coexistence retained

Blockers for broader rollout:

* Live smoke checklist not yet signed off
* Real API/SQL/cloud source validation still manual
* No production usage metrics yet (cannot invent success %)

### Staged rollout (recommended)

```text
developer → internal → selected customers → broader
```

Master kill switch: `ENABLE_CONVERSATIONAL_DATA_SETUP`.

### Required E2E Scenario Matrix

| Scenario | Automated | Manual | Result | Notes |
|----------|-----------|--------|--------|-------|
| Simple file | Yes | Checklist | Pass (auto) | E2E-01 |
| Aggressive clean confirmation | Yes | Checklist | Pass (auto) | E2E-02 |
| Mapping ambiguity | Yes | Checklist | Pass (auto) | E2E-03 mapping update path |
| Return policy | Yes | Checklist | Pass (auto) | E2E-04 + return_policy preserve fix |
| Retry | Yes | Checklist | Pass (auto) | E2E-05 |
| Restart/resume | Yes | Checklist | Pass (auto) | E2E-06 |
| Duplicate dispatch | Yes | Checklist | Pass (auto/partial) | Finalize idempotency |
| Ready→analysis | Yes | Checklist | Pass (auto) | E2E-09/10 |
| REST API | Mocked | Checklist | Pass (mocked) / Manual pending | E2E-11 |
| Database | Mocked | Checklist | Pass (mocked) / Manual pending | E2E-12 |

### Required Observability Matrix

| Signal | Source | Stored/Logged | Purpose |
|--------|--------|---------------|---------|
| step duration | `timed_step` / events | structured log + counters | performance |
| retries | `workflow_steps.attempt` + events | db/log | reliability |
| awaiting_user duration | step timestamps | computed in observability | UX |
| orchestrator fallback | `ORCHESTRATOR_FALLBACK` | log/counters | AI reliability |
| engine rejection | `ORCHESTRATOR_ENGINE_REJECTION` | log/counters | prompt quality |
| workflow ready duration | session created/updated | health summary | overall UX |
| stuck workflows | `find_stuck_workflows` | ops endpoint | ops triage |

### Source-type matrix

| Source | Automated E2E | Manual validation | Result |
|--------|---------------|-------------------|--------|
| CSV | Yes | Checklist ready | Pass (auto) |
| Excel | Indirect (file path) | Checklist | Manual pending |
| REST API | Mocked | Checklist | Mocked pass / manual pending |
| SQL | Mocked | Checklist | Mocked pass / manual pending |
| Cloud | No | Checklist | Not claimed |

## Phase 7 exit criteria

* [x] existing coverage audited
* [x] core file flow has E2E coverage
* [x] confirmation flow has E2E coverage
* [x] retry has E2E coverage
* [x] restart/resume has E2E coverage
* [x] stale/invalidation has E2E coverage
* [x] ready→analysis handoff has E2E coverage
* [x] API source tested or limitation documented
* [x] database source tested or limitation documented
* [x] workflow events/structured logging exist
* [x] step/workflow timing available
* [x] orchestrator fallback/rejection observable
* [x] awaiting_user duration observable
* [x] stuck workflow detection exists
* [x] workflow health summary exists
* [x] failure recovery matrix documented
* [x] security regressions checked
* [x] synthetic fixtures contain no confidential data
* [x] previous Phase 2–6 tests remain green
* [x] new Phase 7 tests pass
* [x] manual smoke checklist exists
* [x] rollout readiness classified (**INTERNAL ONLY**)
* [x] flow.md contains Phase 7 Results

**STOP.** Do not remove the wizard, add multi-agent autonomy, redesign dashboards/analysis, or enable the feature globally without rollout evidence.

# Phase 7.1 Conversational Entry + Token Accounting Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## 1. Entry-flow root cause

Live failure had two concrete causes (not guesswork):

1. **Capabilities race** — FE initialized `conversationalSetupEnabled` from `NEXT_PUBLIC_*` (often unset/false) while `/capabilities` was still in flight. Attach → scan → `setDataSetupSession` took the **wizard-first** branch and auto-rendered `DataSetupCopilot`.
2. **Mapping modal gate** — `useChatSend` called `needsUserApprovedMapping` for attached files **before** chat/orchestrator, even when a `data_setup_session_id` was already present. That opened the column-mapping modal and returned, blocking the Phase 5 Orchestrator path.

Secondary: orchestration payload was not persisted in `chat_messages.response_metadata`, so refresh lost progress/question cards even when the session resumed.

## 2. Files added

* `backend/app/services/orchestrator/usage.py`
* `backend/tests/test_orchestrator_usage.py`
* `src/features/chat/orchestration/entryFlow.test.js`

## 3. Files modified

* `backend/app/services/orchestrator/orchestrator.py` — settle usage on every exit; `setup_intent` / `settlement_key`
* `backend/app/services/orchestrator/decision_models.py` — `llm_usage` on result
* `backend/app/services/chat/llm_client.py` — `safe_chat_completion_with_usage` (primary + fallback records)
* `backend/app/services/quota_service.py` — optional `usage_type` / metadata on existing ledger path
* `backend/app/schemas/chat.py` — `setup_intent`, `client_request_id`
* `backend/app/api/routes.py` — scan/resume WorkflowPlan bootstrap; orchestrated usage on `/chat` + `/chat/stream`
* `backend/tests/test_orchestrator.py`, `backend/tests/test_quota_service.py`
* `src/views/Chat.tsx` — capabilities wait, `setupMode`, kickoff guard, resume, progress, advanced setup
* `src/features/chat/hooks/useChatSend.js` — skip mapping gate; setup_intent; persist orchestration; client_request_id
* `src/features/chat/messageContent.js` — restore orchestration on reload
* `docs/conversational_setup_smoke.md` — Phase 7.1 checklist rows

## 4. Old entry flow

```text
Attach → Scan → DataSetupCopilot auto-open → Review / Approve → Processing
```

## 5. New entry flow

```text
AFTER — Conversational Enabled

Attach
 ↓
Scan / create session (+ WorkflowPlan bootstrap when flag on)
 ↓
Wizard CLOSED (setupMode=conversational)
 ↓
Chat Orchestrator (one kickoff)
 ↓
WorkflowEngine
 ↓
Progress / Tool / Question cards

Advanced Setup
 ↓
DataSetupCopilot (same session)
```

## 6. Feature-flag behavior

| Condition | Behavior |
|-----------|----------|
| Backend `ENABLE_CONVERSATIONAL_DATA_SETUP=true` | Default presentation `conversational`; wizard closed |
| Backend flag false | Wizard-first preserved exactly |
| `NEXT_PUBLIC_*` | Local hint only; `/capabilities` is authoritative |
| FE waits for capabilities before setup routing | Prevents race auto-open |

## 7. Initial orchestrator triggering

After successful scan in conversational mode:

* Preserve `original_prompt`
* `kickConversationalSetup` once (`conversationalKickoffRef` key = `sessionId:prompt|intent`)
* Send → `/chat/stream` with `data_setup_session_id` + `client_request_id`

## 8. Attachment-only behavior

* `setup_intent=prepare_attached_source_for_analysis`
* No fake Thai/English user prose required
* Visible bubble stays attachment-centric (filename / connection name)

## 9. Duplicate-call protection

* Kickoff ref prevents double initial send from React effects
* Usage settlement key `orch:{user}:{session}:{client_request_id}` is idempotent in-process
* Resume effect restores session/workflow **without** auto-kickoff

## 10. Resume behavior

* `GET /data-setup/resume` restores session + full WorkflowPlan progress + `awaiting_user` when flag on
* Wizard remains closed
* Orchestration cards restore from persisted `response_metadata.orchestration` when messages reload

## 11. Wizard manual-open behavior

* Button **ตั้งค่าแบบละเอียด** opens same `DataSetupCopilot` / same session
* Close → refresh session + resume WorkflowPlan → conversational presentation
* No second session / workflow reset

## 12. Old approval compatibility decision

* Conversational path does **not** silently click wizard Approve
* Scan sessions start `awaiting_answers`; Orchestrator → Engine owns steps
* Governance confirmations use Engine `awaiting_user` + `WorkflowQuestionCard`
* Legacy wizard-first sessions unchanged when flag off; in-progress wizard sessions are not force-rewritten on mount

## 13. Existing token accounting system reused

Canonical path remains:

```text
check_user_message_quota → LLM → record_token_usage → RPC increment_profile_tokens
```

No second billing platform. Profile daily/weekly counters stay the quota source of truth.

## 14. workflow_orchestrator usage classification

```text
usage_type = "workflow_orchestrator"
```

Logged on `record_token_usage`; accumulated under `data_setup_sessions.processing_progress.orchestrator_usage` for session aggregation.

## 15. Per-call token accounting

Each real `safe_chat_completion_with_usage` attempt records:

`prompt_tokens`, `completion_tokens`, `total_tokens`, `model`, `fallback`, `repair_attempt`, `kind`

## 16. fallback/repair accounting

| Case | Counted |
|------|---------|
| Primary + rate-limit fallback | Both attempts (usage when available) |
| Structured repair LLM call | Decision + repair |

## 17. Deterministic zero-token paths

* Override / WorkflowPlan fallback / confirmation templates with **no** model call → `llm_calls=0`, no quota increment
* Tool execution (DuckDB/pandas/validate) never adds LLM tokens

## 18. Quota integration

* Orchestrator usage goes through the same `increment_profile_tokens` RPC
* Pre-check still `check_user_message_quota` on `/chat` and `/chat/stream`
* Persist failure is non-fatal (existing policy) — does not corrupt workflow / re-run tools

## 19. Usage idempotency behavior

* Settlement key from `client_request_id` (preferred) or message prefix
* Replay of same key skips second quota increment

## 20. Workflow/session token aggregation

Query `processing_progress.orchestrator_usage` on the session:

```json
{
  "usage_type": "workflow_orchestrator",
  "llm_calls": N,
  "prompt_tokens": ...,
  "completion_tokens": ...,
  "total_tokens": ...
}
```

## Required diagrams

### Entry

```text
BEFORE
Attach → Scan → DataSetupCopilot auto-open → Review/Approve → Processing

AFTER — Conversational Enabled
Attach → Scan/session → WorkflowPlan → Chat Orchestrator → WorkflowEngine → Cards

Advanced Setup → DataSetupCopilot (same session)
```

### Token

```text
Chat setup message
 ↓
AI Orchestrator
 ↓
LlmClient.safe_chat_completion_with_usage
 ↓
provider usage metadata
 ↓
record_token_usage(usage_type=workflow_orchestrator)
```

```text
primary LLM call ─────┐
                      ├→ usage aggregation / settle once
repair/fallback call ─┘
```

```text
WorkflowEngine/template → no LLM → 0 new tokens
```

## Token accounting matrix (implemented)

| Case | Real LLM calls | Token accounting |
|------|----------------|------------------|
| Successful decision | 1 | Count actual usage |
| Primary + fallback | 2 | Count both |
| Structured repair | 2 | Count original + repair |
| Deterministic confirmation template | 0 | 0 |
| WorkflowPlan deterministic fallback | 0 extra | Count only real attempted calls |
| Tool execution | 0 | 0 |
| Ready analysis chat | existing chat LLM | `analysis_chat` (default), not `workflow_orchestrator` |

## 21. Test results

Backend (Phase 2–7.1 relevant): **88 passed** (`orchestrator*`, `workflow*`, `setup_tools`, `e2e/`, usage).  
Frontend orchestration: **34 passed** (normalize, components, chatStream, entryFlow).  
Quota service: green after logger/`detail` fix.

## 22. Manual smoke evidence

* Live browser smoke against a running stack was **not** executed in this agent session (no active API/dev server in terminals).
* Automated E2E + usage unit/integration tests cover orchestrator execution, settlement classification, idempotency, confirmation/resume/ready paths.
* Operator checklist extended in `docs/conversational_setup_smoke.md` (rows A–G).

## 23. Known limitations

* In-process settlement idempotency is per-process (multi-worker duplicates still possible without durable ledger keys — same class of limit as prior chat retries).
* Session `orchestrator_usage` is an ops aggregate, not a formal billing table.
* Manual UI smoke still required before broader rollout.
* Rollout remains **INTERNAL ONLY**; kill switch default false.

## Phase 7.1 exit criteria

* [x] conversational enabled → wizard does not auto-open
* [x] conversational disabled → wizard-first preserved
* [x] original user message reaches Orchestrator
* [x] attachment-only starts conversational setup
* [x] initial orchestrator executes once per logical send
* [x] WorkflowProgress appears from backend state
* [x] actual WorkflowEngine steps advance (E2E / engine path)
* [x] awaiting_user renders conversational card, not wizard review
* [x] refresh restores conversational setup
* [x] wizard remains manually available on same session
* [x] ready sessions use normal analysis path
* [x] existing token/quota system was reused
* [x] orchestrator LLM usage has distinct usage classification
* [x] every real orchestrator LLM call records actual token usage where available
* [x] fallback model calls are also counted
* [x] structured repair calls are also counted
* [x] deterministic templates/fallbacks add zero LLM tokens
* [x] tool execution does not count as LLM usage
* [x] no double counting for the same LLM call (settlement key)
* [x] quota enforcement includes orchestrator usage
* [~] manual smoke proves a real Orchestrator LLM call occurred — **checklist ready; live UI pending**
* [~] manual smoke verifies token usage record — **unit/integration proven; live UI pending**
* [x] frontend tests pass
* [x] backend tests pass
* [x] flow.md contains Phase 7.1 results

**STOP.** Do not remove the wizard, enable globally, increase AI autonomy, add multi-agent behavior, or redesign analysis/dashboard.

# Phase 7.2 State-Aware AI Toolbox Controller + Worklog Stamps Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## 1. Checklist behavior root cause

Validation / Data Contract readiness returns a multi-key `missing` list (`validate_data_contract`). Conversational path previously let the LLM (or raw validator summaries) surface several fields at once — feeling like a hidden form. Wizard `DataSetupCopilot.validateStep` still joins required context, but that is Advanced Setup only.

## 2. Files added

* `backend/app/services/orchestrator/capabilities.py`
* `backend/app/services/orchestrator/working_memory.py`
* `backend/app/services/orchestrator/unresolved.py`
* `backend/app/services/orchestrator/stamps.py`
* `backend/app/services/orchestrator/answer_apply.py`
* `backend/app/services/orchestrator/analytics_adapter.py`
* `backend/app/services/orchestrator/external_adapter.py`
* `backend/tests/test_controller_phase72.py`
* `src/features/chat/orchestration/WorklogStampCard.tsx`

## 3. Files modified

* `orchestrator.py` — controller loop, collect_input, stamps, working memory
* `prompts.py` — Toolbox Controller prompt v2.0
* `decision_models.py` / `decision_parser.py` — `decision_key`, `collect_input` alias
* `session_updates.py` — contract field allowlist
* `ui_payload.py` — `worklog_stamps`, `working_memory`
* `config.py` — `MAX_SETUP_QUESTIONS_PER_TURN`
* FE: `normalize.js`, `OrchestrationMessage.tsx`, `index.js`, tests

## 4. Capability inventory audit

| Capability | Category | Implementation | Authority |
|------------|----------|----------------|-----------|
| inspect…finalize | data_setup | STEP_REGISTRY tools | WorkflowEngine |
| query_data | analytics | question_analytics (DuckDB) | analytics path |
| calculate_metrics | analytics | analytics_service / domain KPIs | analytics path |
| domain_analysis | analytics | domain_analytics | analytics path |
| generate_findings | analytics | structured findings | analytics path |
| evaluate_assurance | analytics | decision_assurance | analytics path |
| web_search | external_context | web_search.py / DDGS | plus/pro + needs_web_search |

## 5–7. Unified model / state-aware rules / Working Memory

`AICapability` + `build_capability_catalog()` derives setup IDs from `STEP_REGISTRY` / `WorkflowPlan.next_action`. Ready → setup inactive, analytics available. `ControllerWorkingMemory` built only from session/plan/tool/stamp truth.

## 8–11. Confirmed context + unresolved + one-question

Confirmed contract fields exposed as `{value, source:user_confirmed}`. Validator `missing` → `UnresolvedDecision` with priority (grain / return / metric… before owner). `MAX_SETUP_QUESTIONS_PER_TURN=1`. Deterministic Thai questions with evidence; collect around validate/finalize (not preempting Engine-approved clean).

## 12–16. Answer parse / authorities / mode switch

`parse_simple_answer` + `apply_decision_answer` → allowlisted `session_updates`. Setup tools only via `WorkflowEngine.execute_step`. Analytics adapter documents DuckDB authority (no arbitrary SQL). Web search eligibility backend-gated. Ready → `mode=analysis` in working memory; analysis execution remains existing chat/DuckDB path (controller does not steal ready traffic).

## 17–19. Worklog stamps

`WorklogStamp` deterministic builders (decision / mapping / tool / analytics / web). Persisted in `processing_progress.worklog_stamps` + orchestration payload. Idempotent `stamp_id`. FE `WorklogStampCard`.

## 20–22. Prompt / leak prevention / tokens

Prompt v2.0 forbids checklists. `strip_raw_validator_checklist` guards assistant text. Controller LLM calls still `workflow_orchestrator`; stamps/deterministic collect = 0 tokens.

## Architecture

```text
User → AI Toolbox Controller → Working Memory + Capabilities
 → ONE decision → Backend authority → Tool/Engine → Stamp → rebuild memory
```

## Capability matrix (implemented)

| Capability | Category | Available when | Authority |
|------------|----------|----------------|-----------|
| inspect…finalize | setup | next executable / deps | WorkflowEngine |
| query_data…assurance | analytics | session ready | existing analytics |
| web_search | external | ready + plus/pro + needs_web | web_search policy |

## Conversation audit (automated)

`test_controller_asks_one_question_not_checklist`: validate-next + empty contract → single `ask_user` with `decision_key`, no “Please provide…” leak; `active_decision` persisted.

## 23. Test results

* `test_controller_phase72.py` + orchestrator/usage/e2e/workflow suites: **green**
* Frontend orchestration: **green** (incl. WorklogStampCard)

## 24. Live smoke results

Live UI smoke not re-run in this agent session. Automated controller + stamp paths proven. Operator should verify with `ENABLE_CONVERSATIONAL_DATA_SETUP=true`: one Thai question → answer → stamp → tool stamp → ready → DuckDB analysis.

## 25. Known limitations

* Ready-session analytics still executes on the existing analysis chat path (by design); catalog exposes analytics capabilities for mode awareness.
* Mapping role questions deferred until mapping exists; not all high-impact roles asked every turn.
* In-process stamp/usage idempotency remains process-local.
* Rollout: **INTERNAL ONLY**.

## Phase 7.2 exit criteria

* [x] capabilities audited + unified AI-safe model
* [x] setup from STEP_REGISTRY/Engine; analytics adapters; web separately governed
* [x] Working Memory + setup/analysis mode
* [x] unresolved decisions + ONE-question + decision_key
* [x] confirmed context + latest results in memory
* [x] one capability per decision; Engine-only setup execution
* [x] WorklogStamp + persistence/idempotency + FE card
* [x] checklist leak prevention + Thai sequential questions
* [x] token accounting unchanged for LLM; stamps free
* [x] prior authority tests green
* [~] live smoke operator checklist remaining
* [x] flow.md Phase 7.2 results

**STOP.** Do not remove the Wizard, enable globally, allow arbitrary tool/SQL calling, increase AI authority over WorkflowEngine, add multi-agent autonomy, or redesign dashboards.

# Phase 7.2.1 Orchestration State Reconciliation & UI Dedup Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## 1. Runtime root cause

Live smoke showed backend progressed while frontend stayed stale until F5. Root causes:

1. **Dual state ownership** — `Chat.tsx` kept `dataSetupWorkflow` / `dataSetupAwaitingUser` separately from per-message `response_metadata.orchestration`, with merge semantics that never cleared `awaiting_user` when absent from stream payloads.
2. **Duplicate live UI** — `OrchestrationMessage` rendered `WorkflowProgress` + interactive `WorkflowQuestionCard` on every assistant message (`isLatest && setupActive`), while `dataSetupCard` in `Chat.tsx` rendered the same controls again.
3. **Stuck submit lock** — `WorkflowQuestionCard` set `pendingValue` on click and never cleared it after success (`finally` intentionally kept lock).
4. **No post-stream reconciliation** — SSE `done` called `onOrchestrationUpdate(orchestration)` only; no `/data-setup/resume` fetch after DB advanced past streamed snapshot.
5. **Historical messages owned live controls** — persisted orchestration metadata with `awaiting_user` remained interactive on latest assistant message.

**Rule (explicit):** Historical orchestration metadata is audit context. Latest backend orchestration state is interactive state. Historical messages must never own active controls.

## 2. Files added

* `src/features/chat/orchestration/reconcileSetupState.js` — canonical `reconcileSetupState`, payload normalization, poll rules, out-of-order guard
* `src/features/chat/orchestration/useSetupReconciliation.js` — React hook for live state + polling
* `src/features/chat/orchestration/CurrentWorkflowPanel.tsx` — singleton live progress + question + blocker
* `src/features/chat/orchestration/ResolvedQuestionSummary.tsx` — read-only historical question
* `src/features/chat/orchestration/reconcile.test.js`
* `src/features/chat/orchestration/reconcile.ui.test.js`

## 3. Files modified

* `src/views/Chat.tsx` — removed split workflow/awaiting state; wired hook + panel; reconcile after answer/stream/resume
* `src/features/chat/ChatMessageList.tsx` — historical-only `OrchestrationMessage`
* `src/features/chat/orchestration/OrchestrationMessage.tsx` — stamps/tool results/resolved questions only (no live progress/question)
* `src/features/chat/orchestration/WorkflowQuestionCard.tsx` — decision lifecycle; reset pending on key change; unlock on failure
* `src/features/chat/orchestration/index.js` — exports
* `backend/app/services/orchestrator/ui_payload.py` — `active_decision`, `resolved_decision_key`, reconciled `awaiting_user`
* `backend/app/api/routes.py` — `/data-setup/resume` returns `active_decision`, stamps, session_status
* `backend/tests/test_orchestrator_ui_payload.py`
* `src/features/chat/orchestration/components.test.js`

## 4. Previous state ownership

| Concern | Before |
|---------|--------|
| Workflow plan | `dataSetupWorkflow` + each `msg.orchestration.workflow` |
| Active question | `dataSetupAwaitingUser` + latest `OrchestrationMessage` |
| Submit lock | `WorkflowQuestionCard.pendingValue` (permanent) |
| Resume | piecemeal `setDataSetupWorkflow` / `setDataSetupAwaitingUser` |
| Stream done | merge orchestration into local state only |

## 5. New source-of-truth model

```text
CurrentOrchestrationState {
  sessionId, sessionStatus, workflowPlan, source,
  activeDecision, awaitingUser, currentBlocker,
  worklogStamps, resolvedDecisionKey, updatedAt
}
```

Backend `/data-setup/resume` + refreshed session `processing_progress.active_decision` = authority. Frontend state is replace-only cache (`?? null` clears).

## 6. reconcileSetupState implementation

`reconcileSetupState({ authFetch, getPublicApiUrl, sessionId, session, conversationId })`:

1. Build resume params from session source_ref  
2. `GET /api/v1/data-setup/resume?...` (state retrieval only — no LLM)  
3. `payloadToCurrentOrchestrationState` replaces live fields  
4. Monotonic sequence guard drops stale responses  

Hook: `useSetupReconciliation` — mount reconcile, conditional poll, `applyStreamOrchestration` for optimistic stream merge before reconcile.

## 7. Stream reconciliation

`handleOrchestrationUpdate` (wired to `useChatSend` stream `done`):

1. `applyStreamOrchestration(streamPayload)`  
2. `reconcileSetup(sessionId)` — backend wins  

## 8. Answer reconciliation

`handleOrchestrationResolve` → chat send → `finally reconcileSetup`. Clears submitting lock via `activeDecision` key change in `CurrentWorkflowPanel`.

## 9. Active decision lifecycle

`pending` → `submitting` (local) → backend persist → `resolved`/cleared → reconcile → next `pending` or running/ready.

Interactive iff `activeDecision.status === 'pending'` AND rendered only in `CurrentWorkflowPanel`.

## 10. Historical question behavior

`OrchestrationMessage` with `historical`: `ResolvedQuestionSummary` (read-only) + optional answer label from following user message. No buttons. Superseded decisions never interactive.

## 11. WorkflowProgress singleton

Exactly one `WorkflowProgress` in `CurrentWorkflowPanel` (`data-testid="current-workflow-panel"`). Removed from per-message rendering.

## 12. Current workflow panel

```text
CHAT TIMELINE (historical stamps/questions/tool summaries)
─────────────────────────
CURRENT WORKFLOW PANEL (singleton)
  WorkflowProgress
  ActiveQuestion (0 or 1)
  Blocker/error (0 or 1)
  Phantom-state recovery UI
─────────────────────────
Composer
```

## 13. Polling fallback

While `sessionStatus` ∈ `{processing, previewing, preview_ready, approved, awaiting_answers}` AND no pending `activeDecision`/`awaitingUser`: reconcile every 1.5s.

## 14. Polling stop rules

Stop on: `awaiting_answers` with pending question, `ready`, `failed`, `cancelled`, unmount.

## 15. Out-of-order protection

Global `reconcileSequence` incremented per call; late responses return `{ stale: true }` and do not apply.

## 16. Backend active-decision contract

`build_orchestration_ui_payload` + `/data-setup/resume` now expose:

```json
{
  "session_id": "...",
  "session_status": "awaiting_answers",
  "active_decision": { "decision_key": "row_grain", "status": "pending" },
  "awaiting_user": { ... },
  "resolved_decision_key": "row_grain"
}
```

After answer: `active_decision: null`, stale `result.awaiting_user` cleared unless `ask_user` decision or plan awaiting remains.

## 17. Inconsistent-state recovery

If `awaiting_answers` but no live question after reconcile: show Thai/EN recovery card with “ลองโหลดสถานะใหม่” → `onReconcile`.

## 18. Error/retry behavior

Submit failure: `WorkflowQuestionCard` clears `pendingValue` in `catch`. Reconcile failure: last known state kept + “กำลังเชื่อมต่อสถานะใหม่…”. Retry via `WorkflowErrorCard` in live panel only.

## 19. Dedup/idempotency behavior

Reconcile is read-only. Stamps remain in timeline. No duplicate LLM calls from polling. Historical orchestration never re-attaches live controls.

## 20. Tests

* FE: `reconcile.test.js` (11), `reconcile.ui.test.js` (5), updated `components.test.js` — **51 FE orchestration tests green**
* BE: `test_orchestrator_ui_payload.py` active_decision/clear tests + orchestrator/workflow/e2e — **green**

Coverage: answer clears active decision, next decision replacement, progress singleton, historical read-only, no duplicate interactive question, out-of-order reconcile, poll uses resume only, failure unlock.

## 21. Live smoke evidence

Automated tests prove reconciliation paths. **Operator live smoke on a fresh session still required** (same checklist as spec Steps 44–46): attach file → question → answer without F5 → one progress → one question → stamp → next action. Prior desynced session not used for proof.

## 22. Token assertion

Polling/reconcile calls `GET /data-setup/resume` only — verified in `reconcile.test.js`. No `/chat/stream` from reconciliation. Token usage unchanged by poll.

## 23. Known limitations

* Live UI smoke not re-run in this agent session (no browser session attached).
* `applyStreamOrchestration` still briefly merges stream snapshot before reconcile (reconcile overwrites).
* Resume requires source_ref params; session-only reconcile fetches session first then resume.
* Rollout: **INTERNAL ONLY**.

## Phase 7.2.1 exit criteria

* [x] backend truth authoritative over frontend orchestration state
* [x] canonical reconciliation function exists
* [x] reconciliation runs after stream completion
* [x] reconciliation runs after decision submission
* [x] reconciliation runs after relevant backend transitions (scan/resume/mount/close advanced)
* [x] backend null `active_decision` clears frontend state
* [x] answered question cannot remain interactive (historical read-only)
* [x] superseded historical questions non-interactive
* [x] exactly one live active question (CurrentWorkflowPanel)
* [x] exactly one live WorkflowProgress
* [x] historical stamps remain visible
* [x] duplicate orchestration cards removed from message timeline
* [x] missing SSE update recovers via safe polling
* [x] polling stops on awaiting_user/ready/failed
* [x] polling does not invoke AI / consume tokens
* [x] out-of-order reconcile cannot regress UI
* [x] answer failure re-enables controls
* [~] no F5 required — **architecture + tests; operator fresh-session smoke pending**
* [~] fresh live smoke question → answer → stamp → next — **operator pending**
* [x] frontend tests pass
* [x] backend regression tests pass
* [x] flow.md contains Phase 7.2.1 results

**STOP.** Do not change WorkflowEngine authority, redesign AI Controller, change Data Contract semantics, add setup tools, change analytics architecture, or enable globally.

# Phase 7.2.2 Submission Boundary + Controller Continuation + Poll Guard + Performance Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## Architecture rules (explicit)

1. Attach != Execute  
2. Send = logical execution boundary  
3. Reconciliation = read state  
4. Controller = progress state  
5. Polling = fallback sync only  
6. WorkflowEngine = setup authority  
7. LLM = conversational/tool controller, not raw executor  

## 1. Attachment auto-execution root cause

`useEffect` in `Chat.tsx` called `GET /data-setup/resume` whenever `selectedFile` changed, binding draft attachments to existing sessions and enabling reconciliation polling before Send. Scan itself only ran on Send via `handleAdaptiveSend → startDataSetup`, but resume-on-attach made setup appear to start immediately.

## 2. Composer submission boundary

- `selectedFile` = draft/staging only (saved as `mode: 'pending'` in chat session storage)  
- Removed `selectedFile` from resume effect dependencies  
- Resume after refresh uses `sessionFileContext.dataSetupSessionId` or non-pending session file only  
- `sendInFlightRef` guards double Enter/Send  
- Scan + orchestrator kickoff only inside `handleAdaptiveSend` after Send  

## 3. Active setup reuse semantics

Scan endpoint returns structured 409:

```json
{
  "code": "ACTIVE_SETUP_EXISTS",
  "existing_session_id": "...",
  "resumable": true
}
```

With `reuse_existing: true` on retry, same-user cross-conversation sessions rebind `conversation_id` and resume. Ready datasets return `READY_DATASET_EXISTS` without silent duplicate creation.

## 4. Controller early-return root cause

After each successful tool, LLM often returned `RespondDecision` narration → orchestrator returned immediately instead of continuing. Frontend polling could not drive WorkflowEngine (read-only), so multi-step progress stalled until another user message.

## 5. run_until_pause implementation

`handle_message` loop (max `MAX_CONTROLLER_ACTIONS_PER_USER_TURN=3`):

- Deterministic next capability when `last_tool_summary.status=completed` and `next_action` is execute/retry (skips LLM)  
- `RespondDecision` after tool success is ignored when `_plan_has_executable_next` — loop continues  
- Stops with explicit `stop_reason`: `awaiting_user`, `ready`, `failed`, `respond`, `action_limit_reached`  
- `setup_intent=continue_workflow` for explicit Continue button  

## 6. Controller stop states

| stop_reason | Meaning |
|-------------|---------|
| awaiting_user | Question persisted |
| ready | Dataset ready |
| failed | Tool/resolution failure |
| respond | No more executable work |
| action_limit_reached | Safety cap; `continuation_available=true` |

## 7. Polling eligibility

`shouldPollSetupState(state)` returns true only when:

- `poll_recommended` from backend, OR  
- `status=processing` AND a workflow step is `running`  

Never polls merely because status is not ready.

## 8. Adaptive backoff

| Elapsed | Interval |
|---------|----------|
| 0–5s | 2s |
| 5–20s | 3s |
| 20–60s | 5s |
| 60s+ | 10s |

## 9. No-progress detection

`buildStateFingerprint` tracks session status, step statuses, active decision, `updated_at`. Same fingerprint ≥4 times → `noProgress=true` → polling stops. UI: “Workflow ยังไม่มีความคืบหน้า” + Continue / Reload.

## 10. Explicit continue behavior

`CurrentWorkflowPanel` “ดำเนินการต่อ” → `POST /chat/stream` with `setup_intent=continue_workflow`. Never triggers execution via `GET /resume`.

## 11. Performance instrumentation

New `ControllerTurnTimer` (`timing.py`) aggregates per-turn:

- `state_load_ms`, `memory_ms`, `llm_ms`, `tool_ms`, `db_ms`, `stamp_persist_ms`  
- Per-iteration summaries  
- Emitted in `audit.performance` + `orchestration.performance`  

## 12–14. LLM / tool / DB timing

Measured via `turn_timer.track(...)` around LLM decide, `execute_step`, session reload, stamp persist. Slow thresholds: `CONTROLLER_SLOW_TURN_MS=30000`, `LLM_SLOW_CALL_MS=15000`, `WORKFLOW_STEP_SLOW_MS=10000`, `DB_SLOW_AGGREGATE_MS=5000`.

## 15. Controller turn summary (automated sample)

| Segment | Duration |
|---------|----------|
| total controller turn | ~1,750 ms (unit timer fixture) |
| state load | ~0 ms (fixture) |
| working memory | ~0 ms (fixture) |
| LLM calls | 1,200 ms |
| WorkflowEngine/tools | 400 ms |
| DB persistence/read | 150 ms |
| other | ~0 ms |

Fixture: `test_controller_turn_timer_summary` — LLM call count 1, stop_reason `awaiting_user`.

## 16. DB chatter optimization

Single `get_workflow_plan` per iteration via `build_orchestrator_llm_context(..., plan=cached)` — removed duplicate plan fetch in same loop pass.

## 17. SSE progress behavior

Not extended in this phase; stream `done` + reconciliation remain primary. `controller_activity` field added to orchestration payload for composer/panel labels.

## 18. Token optimization / redundant LLM audit

Deterministic continuation used when WorkflowPlan `next_action` is execute/retry after tool success — avoids LLM calls whose only purpose is narrating “next step X”. User/business decisions still require LLM or collect_input.

## 19. Frontend long-running UX

`CurrentWorkflowPanel` shows “ยังทำงานอยู่ — ขั้นตอนล่าสุด: {controller_activity}” while `disabled` during generation.

## 20. Tests

* FE: 46 orchestration tests (incl. poll backoff, fingerprint, submission boundary) — **green**  
* BE: `test_controller_phase722.py`, updated orchestrator tests — **green**  

## 21. Live smoke

Operator live smoke pending. Automated evidence: continuation test shows controller runs multiple tool iterations in one turn; poll tests verify resume-only network calls.

## 22. Performance table (unit fixture)

See section 15. Live 1,000-row timing requires operator run with backend logs `audit.performance`.

## 23. Local machine notes

Smoke environment observed ~7.5 GB RAM, ~1.9/2.0 GB swap — may amplify dev latency. Restart dev stack before benchmarking; compare cold vs warm; use `audit.performance` not UI impression.

## 24. Known limitations

* SSE progress events not fully wired (poll remains fallback)  
* Live smoke + real 1,000-row timing table pending operator  
* `action_limit_reached` may require explicit Continue on long setup paths  
* Rollout: **INTERNAL ONLY**

## Phase 7.2.2 exit criteria

* [x] selecting attachment alone does not start setup (resume-on-attach removed)  
* [x] Send/Enter starts exactly one logical request (sendInFlight guard)  
* [x] active same-source setup reuse via structured 409 + `reuse_existing`  
* [x] Controller continues after tool completion without frontend polling  
* [x] reconciliation read-only; polling never drives execution  
* [x] bounded/adaptive polling + no-progress stop  
* [x] explicit Continue via `continue_workflow`  
* [x] controller/LLM/tool/DB timing measured  
* [~] live 1,000-row smoke + timing evidence — operator pending  
* [x] frontend + backend tests green  
* [x] flow.md contains Phase 7.2.2 results  

**STOP.**

---

# Final Closure — AI Agent Workflow

**Status:** CLOSED — DEVELOPMENT OBJECTIVE COMPLETE

**Date:** 2026-08-20
**Authority:** This section supersedes every earlier phase-local `STOP`,
`INTERNAL ONLY`, readiness and pending-smoke status in this document.

## Closure decision

The objective at the top of this document is complete. MataQorLab now has an
AI-orchestrated conversational workflow without transferring deterministic data
authority to the model:

```text
User question/source
  → inspect governed workflow + dataset state
  → AI produces a typed decision or tool request
  → registry/schema/permission/budget validation
  → WorkflowEngine or server-owned analytics executes
  → structured result + provenance + audit ledger
  → one active user decision when clarification is required
  → numeric verification and fail-closed grounding
  → AI narration
```

## Completed scope

* [x] Source inspection, preparation, cleaning, mapping, validation and finalize
  remain deterministic server tools.
* [x] Workflow state, step results, confirmations, retries, idempotency and
  resume behavior persist outside the LLM.
* [x] The AI Orchestrator uses bounded structured decisions and cannot call raw
  workflow handlers directly.
* [x] The unified Agent Tool Registry validates typed inputs, tier/permission,
  dataset context, cost/call budgets, timeouts, retries, idempotency, side
  effects, confirmation requirements and execution environments.
* [x] Core BI and advanced analytical tools return structured evidence for the
  verifier; arbitrary SQL and direct Python execution are not agent tools.
* [x] Exactly one complete pending `active_decision` is authoritative; answered
  questions retire to read-only history and cannot be submitted twice.
* [x] Missing, stale or out-of-order orchestration state fails closed and can be
  recovered through backend reconciliation without giving the browser authority
  to advance tools.
* [x] Chat streaming, branch/regenerate flow, suggested questions and the
  Visualization Chat panel reuse the same guarded send/orchestration path.
* [x] DAX-compatible formula and Python-analysis proposals use explicit review
  boundaries; persistence/sandbox execution requires exact confirmation.
* [x] Required tools that fail do not fall back to model-generated calculations;
  final numeric narration is grounded against server findings.

## Final verification evidence

Focused closure regression executed on 20 Aug 2026:

| Suite | Result | Coverage |
|---|---:|---|
| Backend Agent/Workflow regression | **93 passed** | Tool registry, agent loop, orchestrator decisions/UI/usage, Phase 7.2 controllers, workflow hardening/observability and deterministic conversational E2E |
| Frontend Chat/Orchestration regression | **69 passed across 8 files** | Entry flow, normalization, reconciliation, question cards, branches, suggestions and stream command preservation |

The broader repository verification recorded in `README.md` remains **595
backend tests** and **217 frontend tests across 37 files**, plus TypeScript,
ESLint and the production build. The focused closure run emitted only the known
upstream Supabase client deprecation warnings for `timeout`/`verify`.

## Disposition of historical pending items

The older `[~]` items are not silently marked as live passes:

| Historical item | Final disposition |
|---|---|
| Real Orchestrator LLM + token-record smoke | Moved to authenticated staging release gate; unit/integration accounting is complete |
| Fresh-session question cycles without F5 | Implementation and automated reconciliation regression complete; live operator pass remains a staging UX gate |
| Real 1,000-row timing | Instrumentation is implemented; environment-specific benchmark moved to performance release evidence |
| Live REST API, SQL, Excel and Cloud sources | Mocked/contract coverage complete; credentialed provider checks moved to connector staging certification |
| SSE progress not complete in the historical phase | Read-only bounded polling remains the supported recovery fallback; richer progress streaming is an optional UX enhancement |
| `action_limit_reached` may require Continue | Accepted bounded-agent safety behavior, not an incomplete workflow |
| Engine confirmation vs contract collection states | Preserved as separate authority concepts; confirmed contract collection takes priority by `decision_key` |
| Production usage metrics and broad rollout | Product operations/release work, tracked outside this implementation flow |

## Release boundary

Closing this document does **not** claim that external infrastructure has passed
production certification. Real-auth staging, live provider credentials, Stripe
test lifecycle, Supabase production settings, the isolated Python runner,
observability and rollout metrics remain the release gates documented in
`README.md` and `roadmapmataqorlab.md`.

No additional AI autonomy, raw SQL/Python execution or bypass around
WorkflowEngine is authorized by this closure.

**FLOW CLOSED.**

---

# Phase 7.2.2-update — Composer Turn Lifecycle Fix Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## Architecture rule

**Frontend request lifecycle ≠ Workflow lifecycle**

- Composer locking belongs to an active user HTTP/SSE turn only (`submitting` / `streaming`).
- `awaiting_user` means input is **required** → composer **enabled**.
- Reconciliation/polling never owns the composer lock.

## Lock-state root cause

After SSE `done`, `useChatSend` **awaited** `onOrchestrationUpdate` → `handleOrchestrationUpdate` → `reconcileSetup()` (GET `/data-setup/resume`) **before** `setIsGenerating(false)`.

Symptom: backend at `awaiting_user`, stream complete, but UI still showed Stop / treated generation as active because post-stream reconcile + DB persist held `isGenerating=true`.

Secondary issues:
- `handleOrchestrationResolve` blocked on `isGenerating` (same window).
- `sendInFlightRef` only wrapped `handleAdaptiveSend`, not option/continue paths.
- `AbortError` inner return skipped turn cleanup.

## Files modified

| File | Change |
|------|--------|
| `src/features/chat/chatTurnLifecycle.js` | **NEW** — `finishChatTurn`, `applyStreamOrchestrationUpdate`, `runWithSendInFlight`, stale-lock recovery |
| `src/features/chat/chatTurnLifecycle.test.js` | **NEW** — turn lifecycle unit tests |
| `src/features/chat/hooks/useChatSend.js` | Unlock on SSE done; background orchestration handlers; `turnCleanup` on all exit paths |
| `src/views/Chat.tsx` | `withSendGuard` for all send paths; non-blocking orchestration update; stale-lock watchdog; workflow panel uses `isGenerating \|\| isSendInFlight` |

## Previous lock conditions

- `isGenerating` true during: stream + reconcile + Supabase persist + ready handler
- `CurrentWorkflowPanel` / options: `disabled={isGenerating}`
- `handleOrchestrationResolve`: `if (isGenerating) return`
- Send button: Stop whenever `isGenerating`

## New turn lifecycle

```
idle → (Send/option) → submitting/streaming (isGenerating=true)
  → SSE done → idle immediately (finishChatTurn)
  → applyStreamOrchestration (sync)
  → reconcileSetup (background, void)
  → DB persist (background, no composer lock)
```

`withSendGuard` / `sendInFlightRef` prevents duplicate logical sends until `handleSend` promise settles; does **not** disable composer after stream ends.

## sendInFlight cleanup

- `withSendGuard`: `finally { sendInFlightRef=false; isSendInFlight=false }`
- Covers: composer Send, option resolve, continue workflow
- `runWithSendInFlight` tested for early-return and error paths

## SSE done behavior

`turnCleanup()` runs immediately after final message is applied — **before** orchestration update, ready handler, or Supabase persist.

## awaiting_user behavior

- Composer enabled when `isGenerating=false` (immediate after stream).
- `CurrentWorkflowPanel` shows active question.
- No Stop button unless a real stream is active.

## Option / free-text coexistence

- Option buttons: temporarily busy via panel `submitting` + `isSendInFlight` during request only.
- Free-form composer: enabled on `awaiting_user`; `withSendGuard` blocks duplicate Enter/Send.

## Send / Stop button semantics

- **Send** when `isGenerating=false`
- **Stop** only when `isGenerating=true` (active SSE stream)
- Not tied to workflow `awaiting_user`, `activeDecision`, or reconciliation

## Reconciliation independence

`applyStreamOrchestrationUpdate` applies stream payload synchronously; `void reconcileSetup(...)` — polling/reconcile never sets `isGenerating`.

## Abort / error cleanup

- `stopGeneration` → `turnCleanup()`
- `AbortError` → `turnCleanup()` before return
- Stream failure catch → `turnCleanup()`
- Stale-lock watchdog: if `isGenerating` without active `abortControllerRef` for 500ms → recover

## Tests

* `chatTurnLifecycle.test.js` — 8 tests (unlock order, background reconcile, send guard, stale recovery) — **green**
* Full FE suite — **189 tests green**
* BE orchestration/controller regression — **green**

## Live smoke

Operator live smoke pending (Steps 26–29). Automated evidence covers unlock-before-reconcile ordering and send-guard invariants.

## Known limitations

* Live 3+ question-cycle smoke pending operator confirmation
* `startDataSetup` scan still briefly sets `isGenerating` (separate from chat stream; acceptable)
* Rollout: **INTERNAL ONLY**

## Phase 7.2.2-update exit criteria

* [x] frontend turn lifecycle explicit (`chatTurnLifecycle.js`)
* [x] composer disabled only during active user request/stream
* [x] `awaiting_user` leaves composer enabled
* [x] `activeDecision` does not disable free-form typing
* [x] option answers work (via `withSendGuard`)
* [x] free-form answers work
* [x] sendInFlight always clears in `finally`
* [x] every completed turn unlocks composer on SSE done
* [x] reconciliation/polling does not lock composer
* [x] Stop only during real active stream
* [x] stream error / abort unlock composer
* [x] double Send prevented
* [x] attachment draft semantics unchanged
* [~] 3+ consecutive question cycles without F5 — operator pending
* [x] frontend tests pass
* [x] backend regression tests green
* [x] flow.md contains update results

## Hotfix — stale setup on deleted / new chat (2026-08-08)

**Symptom:** `/chat/new` showed workflow from deleted conversation (resume by file name + uncleared `dataSetupSession`).

**Fix:** `onWorkspaceReset` clears `dataSetupSession`/orchestration on `startNewChat`; block file-only resume without `conversation_id`; don't restore localStorage file scoped to old conversation on fresh new chat; clear localStorage on delete.

---

# Phase 7.2.2-update2 — Decision / Tool Alignment Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## Root cause

1. **Mismatched questions:** AI message from stream/`awaiting_user` could differ from persisted `active_decision`; frontend `deriveLiveAwaitingUser` returned stale `awaitingUser` verbatim when present.
2. **Generic validate approval:** `ConfirmationRequired` on validate used `_ask_from_awaiting()` templates instead of `unresolved.py` business decisions (e.g. row_grain).
3. **Incomplete active_decision:** Persist wrote only `{decision_key, question, options}` — missing `status`, `expected_input`, `free_text_allowed`; `ConfirmationRequired` path never persisted `active_decision`.
4. **Dead-end UI:** `WorkflowQuestionCard` fallback `"เลือกตัวเลือกเพื่อดำเนินการต่อ"` when question empty but options existed.

## Files changed

| Area | Files |
|------|-------|
| Backend contract | `answer_apply.py` — `build_active_decision_payload`, `validate_active_decision_completeness`, fail-closed persist |
| Controller | `orchestrator.py` — full payload persist; validate `ConfirmationRequired` → unresolved; `validate_blocked` ignores `just_finished_tool` |
| Validator | `decision_validator.py` — preserve `decision_key`, `expected_answer_type` |
| UI payload | `ui_payload.py` — completeness gate, `incomplete_active_decision`, extended fields |
| Frontend | `reconcileSetupState.js`, `WorkflowQuestionCard.tsx`, `CurrentWorkflowPanel.tsx` |
| Tests | `test_controller_phase722_update2.py`, updated `reconcile.test.js`, `components.test.js` |

## active_decision contract

Every pending decision includes:

- `decision_key`, `question`, `status: pending`
- `expected_input`: `single_choice` | `free_text` | `option_or_text`
- `free_text_allowed: true` (default)
- `options[]` when structured choice available

Fail-closed: incomplete decisions rejected at persist + UI payload (`incomplete_active_decision`).

## Validator → unresolved flow

```
validate_data (evidence only, status=awaiting_user)
  → orchestrator validate_blocked
  → resolve_unresolved_decisions / select_one_decision
  → ONE Thai question (e.g. row_grain)
  → build_active_decision_payload
  → persist + assistant_message = same question
```

`ConfirmationRequired` on validate/map/prepare/inspect redirects to unresolved when available — no generic "approve validate".

## Frontend render rule

- Live question **only** from pending `active_decision` via `deriveLiveAwaitingUser` (active fields win over stale `awaiting_user`).
- No generic fallback text — missing question → recovery card (`phantomAwaiting`).
- Composer stays enabled when `free_text_allowed` (default true).

## Tests

* BE: `test_controller_phase722_update2.py` — row_grain not validate approval, completeness, fail-closed payload, ConfirmationRequired → unresolved — **green**
* FE: 196 tests — deriveLiveAwaitingUser override, incomplete decision, no generic fallback — **green**
* BE regression: orchestrator/controller suites — **green**

## Live smoke

Operator pending. Expected: AI + panel show same row_grain question with Thai options + free-text composer.

## Known limitations

* Live smoke not yet operator-confirmed
* Rollout: **INTERNAL ONLY**

**STOP.**

---

# Phase 7.2.2-update3 — Resolved Decision Retirement + Option Preservation Results

**Status:** COMPLETE (INTERNAL ONLY)  
**Date:** 2026-08-08

## Root cause

1. **Re-ask after answer:** Collect-input answers were blocked when `workflow_plan.awaiting_user` was set (engine confirmation). Answer path skipped → stamp from a partial apply OR next turn re-generated `row_grain` because resolver only checked contract fields, not persisted `confirmed_decisions`. Tool stamp persist re-wrote stale `active_decision` from in-memory session snapshot.
2. **Missing option buttons:** `/data-setup/resume` built slim `active_decision` without `expected_input` / full options; FE treated `options: []` as authoritative (no fallback); `single_choice` with empty options passed completeness gate in FE.

## Files changed

| Area | Files |
|------|-------|
| Decision identity | `decision_identity.py` (NEW) — fingerprint, `is_decision_confirmed`, `record_confirmed_decision` |
| Resolver | `unresolved.py` — skip confirmed decisions via persisted truth + contract |
| Answer apply | `answer_apply.py` — retire `active_decision`, set `resolved_decision_key`, `confirmed_decisions`; `persist_stamps_only` |
| Working memory | `working_memory.py` — `confirmed_context` from `confirmed_decisions` + contract |
| Controller | `orchestrator.py` — apply collect answers even when plan `awaiting_user`; reload session after apply; stamps-only persist |
| UI payload | `ui_payload.py` — no plan `awaiting_user` resurrection when `active_decision` null; `resolved_decision_key` from progress |
| Resume API | `routes.py` — use `_session_active_decision`; explicit `awaiting_user: null` when no pending decision |
| Frontend | `reconcileSetupState.js`, `WorkflowQuestionCard.tsx` |
| Tests | `test_controller_phase722_update3.py`, updated `reconcile.test.js` |

## Decision retirement flow

```
row_grain pending (active_decision persisted)
  → user answers (collect_input — not blocked by engine awaiting_user)
  → apply_decision_answer: contract update + record_confirmed_decision
  → active_decision cleared, resolved_decision_key=row_grain
  → reload session from DB
  → rebuild working memory
  → resolver skips row_grain (is_decision_confirmed)
  → next unresolved (e.g. primary_metric) OR next capability
```

Never reuse pre-answer `active_decision` snapshot. Tool stamps use `persist_stamps_only` (no active_decision mutation).

## Confirmed-context filtering

Before creating `UnresolvedDecision`, `is_decision_confirmed(session, key)` checks:

- `processing_progress.confirmed_decisions[key].source == user_confirmed`
- value present
- fingerprint matches current context (mapping + contract + source)
- falls back to contract/mapping truth when no stale fingerprint mismatch

Applies to all decision keys (`row_grain`, `primary_metric`, `return_policy`, `mapping:*`, etc.) — not row_grain-only.

## Decision identity / fingerprint

`decision_context_fingerprint(session, decision_key)` hashes session_id, source_fingerprint, mapping_fp, contract_fp (+ role for `mapping:*`).

Re-open pending only when fingerprint changes (source/mapping/contract invalidation) or user explicitly changes confirmed value (version increment on re-record).

## Option-preservation path

```
unresolved._question_for (backend owns Thai options)
  → build_active_decision_payload (validate completeness)
  → processing_progress.active_decision (full payload)
  → ui_payload._session_active_decision
  → /data-setup/resume (full options + expected_input)
  → FE normalizeActiveDecision (non-empty options only; no FE recreation)
  → CurrentWorkflowPanel → WorkflowQuestionCard
```

`single_choice` / `option_or_text` require `options.length > 0` — else `INCOMPLETE_ACTIVE_DECISION` + recovery UI.

## /resume behavior

- Backend `active_decision` wins; explicit `null` clears FE state
- No merge of historical `plan.awaiting_user` or stale orchestration metadata
- `resolved_decision_key` surfaced from progress

## Frontend render rules

- Interactive controls only from pending backend `active_decision` via `deriveLiveAwaitingUser`
- `active_decision: null` → `awaitingUser: null` (no resurrection)
- `expected_input=single_choice` + `options=[]` → incomplete → recovery card (`ข้อมูลคำถามไม่สมบูรณ์` / `โหลดสถานะใหม่`)
- Historical worklog stamps remain read-only; resolved questions do not reappear as interactive

## Tests

* BE: `test_controller_phase722_update3.py` — confirmed skip, retirement, next decision, options persist, refresh clear, single_choice incomplete, collect despite plan awaiting — **green**
* BE regression: update2, phase72, ui_payload — **green**
* FE: `reconcile.test.js` — no resurrection, options preserved, single_choice incomplete — **green**

## Live smoke

Operator pending. Expected on fresh session:

1. AI + panel show same row_grain question with `[ใช่ — รายการในบิล]`, `[ไม่ใช่ — ทั้งบิล]`, `[อย่างอื่น]`
2. User selects invoice_line → `✓ บันทึกแล้ว row_grain = invoice_line`
3. row_grain never reappears as interactive question
4. Controller advances to next unresolved decision or capability without F5
5. No empty question card / missing buttons

## Known limitations

* Live smoke not yet operator-confirmed on fresh session
* Engine-level `awaiting_user` (validate confirm) still separate from contract collect — collect now takes priority when `decision_key` present
* Rollout: **INTERNAL ONLY**

**STOP.**

---

# Document End — Authoritative Status

**FLOW CLOSED — DEVELOPMENT OBJECTIVE COMPLETE (20 Aug 2026).**

The Phase 7.2.2 update records immediately above are historical append-only
evidence. They do not reopen the flow or override the Final Closure decision.
Any credentialed staging, infrastructure certification or production rollout
work is a release gate tracked in `README.md` and `roadmapmataqorlab.md`, not an
unfinished AI Agent implementation phase.

เนื้อหา Phase 7.2.2 update ด้านบนเป็นหลักฐานย้อนหลัง ไม่ได้เปิด Flow ใหม่หรือ
แทนที่ Final Closure งานที่ต้องใช้ Credential, Staging Infrastructure หรือ
Production rollout เป็น Release Gate ใน `README.md` และ
`roadmapmataqorlab.md` ไม่ใช่งานพัฒนา AI Agent ที่ค้างใน Flow นี้

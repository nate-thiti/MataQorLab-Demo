# Conversational Data Setup — Manual Smoke Checklist (Phase 7 / 7.1)

Use a **dev** environment only. Synthetic CSV fixtures live in `backend/tests/fixtures/workflow/`.

## Preconditions

1. Backend + worker running
2. Supabase migrations applied (`workflow_steps`, `workflow_begin_step_ready`)
3. Set `ENABLE_CONVERSATIONAL_DATA_SETUP=true` in backend env
4. Confirm `GET /api/v1/capabilities` returns `"conversational_data_setup": true`
5. Optional FE hint: `NEXT_PUBLIC_ENABLE_CONVERSATIONAL_DATA_SETUP=true`

## Phase 7.1 entry + token checks

| # | Step | Pass? | Notes |
|---|------|-------|-------|
| A | Attach file + text — wizard does **not** auto-open | ☐ | Progress in chat |
| B | Attachment-only starts setup (no second message) | ☐ | `setup_intent` path |
| C | Initial orchestrator LLM call recorded | ☐ | `usage_type=workflow_orchestrator` |
| D | Aggressive confirm → deterministic card, 0 new tokens if no LLM | ☐ | |
| E | Refresh mid-flow — wizard closed, question restored | ☐ | No duplicate kickoff |
| F | ตั้งค่าแบบละเอียด → same session → close → conversational | ☐ | |
| G | Ready → analysis question uses analysis-chat accounting | ☐ | Not workflow_orchestrator |

## File flow checklist

| # | Step | Pass? | Notes |
|---|------|-------|-------|
| 1 | Enable conversational flag | ☐ | Restart API after env change |
| 2 | Upload `sales_clean.csv` | ☐ | Attach in Chat |
| 3 | Confirm progress cards appear | ☐ | Backend-grounded steps |
| 4 | Trigger aggressive clean confirmation | ☐ | Use Deep Clean / aggressive profile |
| 5 | Choose Reject or Use Standard | ☐ | Structured resolution; no double-submit |
| 6 | Refresh browser mid-flow | ☐ | Session resumes; wizard still available |
| 7 | Resume continues from workflow state | ☐ | No duplicate clean if artifact present |
| 8 | Force retryable failure (dev tool/fault) | ☐ | Or simulate via ops |
| 9 | Click Retry | ☐ | Chat → Orchestrator → Engine |
| 10 | Reach ready | ☐ | Ready card + assurance layers |
| 11 | Ask analysis question | ☐ | e.g. ยอดขายรวมเท่าไหร่ |
| 12 | Confirm analysis path | ☐ | Not conversational setup routing |

## Advanced / wizard coexistence

| # | Step | Pass? |
|---|------|-------|
| 13 | Open “ตั้งค่าแบบละเอียด” | ☐ |
| 14 | Change mapping in wizard | ☐ |
| 15 | Return to chat; next turn reflects stale/replan | ☐ |

## API / Database (manual)

| Source | Steps | Pass? | Notes |
|--------|-------|-------|-------|
| REST API | scan → conversational setup → ready → analysis | ☐ | Use internal mock/staging API |
| SQL | select table → setup → ready → analysis | ☐ | Dev Postgres/SQLite provider |
| Cloud | document only if unavailable | ☐ | Do not claim Pass without run |

## Observability checks

| Check | Pass? |
|-------|-------|
| Structured logs include `session_id`, `step_type`, `duration_ms` | ☐ |
| `GET /api/v1/ops/workflow-health` (org admin) returns summary | ☐ |
| Stuck detection reasons appear for long-running test session | ☐ |
| No credentials/storage paths in UI orchestration payload | ☐ |

## Kill switch

| Check | Pass? |
|-------|-------|
| Set flag false → wizard-first path returns | ☐ |
| Ready sessions still use analysis chat | ☐ |

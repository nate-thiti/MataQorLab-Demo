# Supabase SQL migrations

Run these scripts in the **Supabase SQL Editor** (in order) for each environment (staging/production).

| Order | File | Purpose |
|------:|------|---------|
| 1 | `profiles_timezone.sql` | Adds `profiles.timezone` (IANA) for local-midnight quota resets |
| 2 | `profile_quota_rpc.sql` | RPC functions: `refresh_profile_quota`, `check_user_message_quota`, `increment_profile_tokens`, `_quota_limit_error` |
| 3 | `profiles_column_security.sql` | Private privileged quota functions + public wrappers; restrict browser profile updates |
| 4 | `chat_messages_web_sources.sql` | Persists citation cards with assistant messages |
| 5 | `chat_intelligence.sql` | Adds scoped memory, answer verification metadata, model/search traces, and quality feedback |
| 6 | `advisor_hardening.sql` | Hardens RLS, function access, and advisor-reported indexes |
| 7 | `analysis_audit_feedback.sql` | Adds dataset semantic metrics and finding-level feedback; extends quality-event RLS |
| 8 | `memory_fact_only_cleanup.sql` | One-way removal of legacy LLM prose memory after computed-fact migration |
| 9 | `etl_workflows.sql` | Owner-only ETL recipes/runs/schedules, one stable output dataset identity per schedule, immutable output versions, replica-safe leases and quality alerts |
| 10 | `cloud_dataset_connections.sql` | Google/Microsoft linked datasets with owner-only RLS and versioned ETL output references |
| 11 | `customer_storage_quota.sql` | Unified per-customer Storage + Postgres usage, locked quota enforcement and backend-only business-data uploads |
| 12 | `visualization_reports.sql` | Private Visualization reports/chart snapshots, owner RLS, conversation provenance and quota accounting |
| 13 | `automation_guardrails.sql` | Owner-private scheduled-delivery candidate decisions, dedup fingerprints, suppression reasons, cost/open telemetry and RLS |
| 14 | `dynamic_visualization_dashboards.sql` | Adaptive BI source contract and per-report filter/widget/layout specification |
| 15 | `visualization_revisions_shares.sql` | Dashboard revision history, reusable templates, and revocable expiring read-only share links |
| 16 | `scheduled_delivery_hardening.sql` | SMTP delivery/open/failure telemetry, evidence-bounded narration fields, semantic KPI gates and share view-limit lifecycle |
| 17 | `organization_workspace_memory.sql` | Organization/workspace tenancy, memberships, typed company memory, approval, revisions, audit, rollback and read-only browser RLS |
| 18 | `organization_workspace_memory_fk_index.sql` | Covering index for the governed-memory workspace/organization composite foreign key |
| 19 | `enterprise_self_service.sql` | Enterprise plan seed plus server-owned subscription seat counts (minimum enforced by checkout) |
| 20 | `enterprise_base_seat_pricing.sql` | USD 99 organization base price including two seats, then USD 39 per additional seat |
| 21 | `enterprise_business_onboarding.sql` | Private Stripe mapping and service-role-only atomic Organization/General Workspace provisioning |
| 22 | `customer_experience_platform.sql` | Backend-only customer onboarding, source health, lineage, collaboration, alerts, organization invitations, integration contracts and embed configuration |
| 23 | `customer_experience_onboarding_report_fk_index.sql` | Covering index for onboarding progress references to the first generated dashboard |
| 24 | `smart_alert_evaluator.sql` | Smart Alert source filters, evaluation schedule, atomic worker leases, idempotency keys and delivery evidence |
| 25 | `weekly_chat_delivery.sql` | Weekly Monday–Sunday AI analysis into one owned chat per dataset, with database-enforced duplicate prevention and exact-once message delivery |
| 26 | `etl_mapping_contract_hardening.sql` | Dataset-scoped mapping memory with column business metadata, explicit Data API grants and owner-only RLS |
| 27 | `workflow_steps.sql` | Per-step workflow persistence for Data Setup resume (child of `data_setup_sessions`; apply after adaptive setup + hardenings) |
| 28 | `workflow_begin_step_ready.sql` | Phase 4.5: reclaim `ready` confirmation rows in `begin_workflow_step` (apply after 27) |

Run `profiles_column_security.sql` immediately after `profile_quota_rpc.sql`; it
moves the privileged implementations into the non-exposed `private` schema.
Use the normal migration history for later changes rather than re-running these
bootstrap scripts on an existing environment.

## After running

- **Backend** must be redeployed so `quota_service.py` calls the RPCs and records usage after chat.
- **Frontend** uses the same RPCs via `src/utils/profileQuota.js`.

## Verify

```sql
SELECT proname FROM pg_proc
WHERE proname IN (
  'refresh_profile_quota',
  'check_user_message_quota',
  'increment_profile_tokens'
);
```

Send one chat message and confirm `profiles.tokens_used_today` increases once (backend increment, not doubled by the client).

Parallel tabs near the limit: `increment_profile_tokens` re-checks limits in the same transaction (row locked via `refresh_profile_quota`) and returns `status: error` without incrementing when over limit.

## Tests

```bash
npm test                    # frontend: timezone + profileQuota (vitest)
cd backend && pytest tests/test_quota_service.py
```

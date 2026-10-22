# Error Taxonomy and Logging Contract

Critical paths use JSON logs and stable `error_code` values. Raw exception text stays in server logs and must not be returned to customers.

| Error code | Meaning | Retryable | Expected handling |
|---|---|---:|---|
| `dependency_unavailable` | Supabase, LLM, SMTP, or provider dependency is unavailable | Yes | Preserve existing data, emit warning/error, retry only where idempotent |
| `source_operation_failed` | File/API/SQL discovery, fetch, or sync failed | Yes | Fail closed; do not publish or overwrite output |
| `persistence_failed` | A required report/revision/audit write failed | Yes | Required writes fail the operation; explicitly optional telemetry logs a warning |
| `scheduler_failed` | ETL/Alert/Scheduled delivery job failed | Yes | Record failed state, release lease, retain run/job ID |
| `billing_operation_failed` | Stripe checkout, webhook, or subscription action failed | No by default | Do not retry synchronously unless Stripe idempotency permits it |
| `internal_error` | Unclassified programming/runtime failure | No | Return generic incident response and investigate |

## Structured event requirements

Every critical error event contains `timestamp`, `level`, `logger`, `event`, `correlation_id` when request-scoped, `job_id` when job-scoped, and a stable `error_code`. Add safe identifiers such as `report_id`, `schedule_id`, and `run_id`; never log JWTs, provider credentials, request bodies, raw rows, or Stripe signatures.

## Broad exception audit rule

`except Exception` is allowed only at one of these boundaries:

1. API/process boundary that logs and converts to a generic incident response.
2. Job boundary that records failed state and releases its lease.
3. Explicitly optional telemetry/cache/fallback path that logs a warning and cannot alter correctness.
4. Provider adapter boundary that wraps the exception in a domain error without exposing secrets.

Critical Source, Visualization save/planner, Scheduler, Smart Alert, and Billing paths were moved off `print` and onto this contract. New `print` calls in those modules are rejected by regression tests.


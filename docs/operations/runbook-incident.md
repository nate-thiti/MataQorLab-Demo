# Incident Runbook

1. Capture correlation ID from the failing UI/API response.
2. Search API and worker JSON logs for that `correlation_id`.
3. Classify with `docs/operations/error-taxonomy.md`.
4. If a background job failed, inspect `/api/v1/ops/dead-letters`.
5. Mitigate: pause scheduler (`ETL_SCHEDULER_ENABLED=false`), revoke bad share/grant, or roll back deploy.
6. Record timeline in `docs/operations/postmortem-template.md`.

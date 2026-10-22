# P2 Service Level Objectives
#
# These targets are measured by `sli_sample` log events from
# `backend/app/services/sli.py`. Staging and production should alert when the
# rolling 7-day success rate for any workflow drops below the error budget.

| Workflow | SLI | Target | Error budget |
|---|---|---|---|
| Upload | `upload` latency to durable storage ACK | p95 ≤ 5s | 1% of requests over target / 7d |
| Quick scan | `quick_scan` latency to Data Setup scan/approve handoff | p95 ≤ 8s | 2% / 7d |
| ETL / Data Setup materialize | `etl` latency to DatasetVersion ready | p95 ≤ 120s | 5% / 7d |
| Chat | `chat_ttfb` time to first assistant token | p95 ≤ 3s | 2% / 7d |
| Dashboard | `dashboard` latency for cached DatasetVersion generate | p95 ≤ 4s | 2% / 7d |

## Measurement

- Emit `sli_sample` JSON logs with `workflow`, `duration_ms`, `outcome`, `within_slo`.
- Aggregate by workflow + environment in the log platform.
- Page on-call when error budget burn exceeds 2× the weekly budget in 1 hour.

## Ownership

- Product spine (upload/scan/ETL/chat/dashboard): backend + worker owners
- Isolation failures (cross-tenant access): security/on-call

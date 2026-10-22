# MataQorLab Bug Registry

This is the canonical register for functional, reliability, security, and data-correctness defects. GitHub issues hold investigation detail; this file records release-blocking state.

## Severity and response

| Severity | Definition | Initial response | Release rule |
|---|---|---:|---|
| P0 | Cross-tenant exposure, data loss/corruption, auth bypass, payment corruption, or critical production outage | 15 minutes | Stop release; incident commander and postmortem required |
| P1 | Critical workflow unavailable, repeated/incorrect delivery, materially wrong verified result, or no safe workaround | 4 hours | Fix or explicitly remove affected capability before release |
| P2 | Degraded workflow with a safe workaround and no correctness/security impact | 1 business day | Prioritize in current/next sprint |
| P3 | Cosmetic, copy, or low-impact usability issue | 3 business days | Normal backlog |

## Required lifecycle

`reported → triaged → reproduced → fixing → verifying → closed`

A defect is closed only when the fix, regression test, environment evidence, and deployment/retest result are linked. P0/P1 defects also require an owner and target release. Reopened defects retain their original ID.

## Active register

| ID | Severity | State | Owner | Environment | Summary | Evidence / exit condition |
|---|---:|---|---|---|---|---|
| SEC-001 | P0 | Open | Unassigned | Live Supabase | Leaked Password Protection disabled | Advisor WARN cleared and authentication smoke test passes |
| OPS-001 | P0 | Open | Unassigned | Production | SMTP, Stripe Live, and worker smoke evidence incomplete | Provider events and worker heartbeat/run IDs retained |
| REL-001 | P0 | Closed | Engineering | Staging | Real end-to-end release gate | Clean Upload → Mapping → Chat → Visualization → Save/Reopen verified; retain evidence on every release |
| REL-002 | P1 | Hardening | Engineering | All | Silent fallback and broad exception audit | Critical paths comply; complete secondary-module audit without regressions |
| BUG-001 | P1 | Closed | Engineering | Browser | Dashboard filter required refresh | Browser regression passed; backend reports filtered row count |
| BUG-002 | P1 | Closed | Engineering | Browser | PNG/PDF export failed on cross-origin stylesheet | Browser/unit regression passed with safe font traversal disabled |

## Intake fields

Every linked issue must include:

- Environment and release/commit
- User ID and Organization ID (redacted when exported)
- Source identity and Dataset key
- Browser `X-Correlation-ID`, API request ID, job/run ID, and provider event ID where applicable
- UTC timestamp and timezone seen by the user
- Reproduction steps, expected result, actual result
- Screenshot/log excerpt with secrets and customer data removed
- Data-loss, security, billing, duplicate-delivery, and cross-tenant impact assessment
- Regression test and verification evidence

## P0 response process

1. Stop deployments and unsafe automation; preserve evidence.
2. Assign incident commander, technical owner, and communications owner.
3. Contain exposure without deleting logs or source snapshots.
4. Correlate Browser → API → Job → Supabase/provider using the same incident identifiers.
5. Restore service through a reversible change and run correctness/isolation smoke tests.
6. Publish an internal timeline and complete a blameless postmortem within five business days.

# Canonical E2E scenarios (Phase 7)

Synthetic fixtures only — no confidential business data.

| ID | Scenario | Fixture | Expected |
|----|----------|---------|----------|
| E2E-01 | Simple clean file | `sales_clean.csv` | inspect→prepare→map→validate→clean→finalize→ready |
| E2E-02 | Aggressive clean confirmation | dirty/returns + profile=aggressive | awaiting_user before clean; modify→standard→clean |
| E2E-03 | Ambiguous mapping | `sales_mapping_ambiguous.csv` | ask_user/awaiting for PRICE_LEVEL; map update; validate rerun |
| E2E-04 | Return policy / business context | `sales_returns.csv` | user confirms negatives=returns; contract updated |
| E2E-05 | Tool failure + retry | forced clean fail then success | failed attempt1; attempt2 completed; ready |
| E2E-06 | Backend restart / resume | seed prepare/map/clean completed | new engine reuses; finalize only |
| E2E-07 | Duplicate worker dispatch | double finalize/execute | reuse/idempotent; one publish |
| E2E-08 | Stale after config change | complete then change mapping | validate stale; clean remains valid |
| E2E-09 | Ready → analysis chat | session ready | orchestrator not routed |
| E2E-10 | Feature flag disabled | flag=false | no conversational routing |
| E2E-11 | API source | mocked source_type=api | plan/fingerprint path (CI mock) |
| E2E-12 | Database source | mocked source_type=sql | plan/fingerprint path (CI mock) |

# Backup & Restore Runbook

## Targets

- RPO: 24h for Postgres + Storage metadata
- RTO: 4h for staging restore drill, 8h for production

## Drill

1. Create a Supabase backup/PITR restore into a temporary project.
2. Restore Storage bucket inventory for one owner folder.
3. Point a staging API at the restored project with read-only credentials.
4. Verify conversations, dataset catalog, visualization reports, and one ETL recipe.
5. Record evidence under `docs/operations/evidence/` with date, operator, RPO/RTO measured.

# Rollback Runbook

1. Identify the last healthy deploy SHA from Render/GitHub.
2. Roll web and API to that SHA together; keep worker on the same SHA.
3. Do not reverse Supabase migrations that already created tables; instead disable new routes/features with env flags if needed.
4. Verify `/health/ready`, login, `/api/v1/files`, and one dashboard generate.
5. If Data Setup jobs are stuck, leave them in DLQ and replay after the healthy build is confirmed.

from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "p0_data_flow_security_hardening.sql"
).read_text(encoding="utf-8").lower()


def test_connector_tables_are_backend_only_and_setup_is_idempotent():
    assert "secrets_encrypted text" in SQL
    assert "revoke all on table public.api_connections from public, anon, authenticated" in SQL
    assert "revoke all on table public.database_connections from public, anon, authenticated" in SQL
    assert "idx_data_setup_sessions_one_active_source" in SQL


def test_etl_run_audit_is_immutable_for_customer_roles():
    assert "revoke insert, update, delete, truncate on public.etl_pipeline_runs from authenticated" in SQL
    assert "grant update (acknowledged_at) on public.etl_quality_alerts to authenticated" in SQL


def test_data_setup_claims_support_opaque_service_keys_without_browser_access():
    assert SQL.count("security invoker") >= 2
    assert "current_setting('request.jwt.claim.role'" not in SQL
    assert (
        "revoke all on function public.claim_data_setup_session(uuid)"
        in SQL
    )
    assert (
        "grant execute on function public.claim_data_setup_session(uuid) to service_role"
        in SQL
    )

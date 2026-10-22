from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "adaptive_data_setup_copilot.sql"
).read_text(encoding="utf-8").lower()


def test_data_setup_session_table_is_owner_scoped_and_sample_safe():
    assert "create table if not exists public.data_setup_sessions" in SQL
    assert "enable row level security" in SQL
    assert "auth.uid()) = user_id" in SQL
    assert "revoke all on public.data_setup_sessions from public, anon, authenticated" in SQL
    assert "grant select on public.data_setup_sessions to authenticated" in SQL
    assert "sample_rows" not in SQL
    assert "processing_progress jsonb" in SQL


def test_data_setup_foreign_keys_have_supporting_indexes():
    assert "idx_data_setup_sessions_conversation" in SQL
    assert "idx_data_setup_sessions_recipe" in SQL
    assert "idx_data_setup_sessions_run" in SQL


def test_data_setup_jobs_use_service_role_only_atomic_claims():
    assert "for update skip locked" in SQL
    assert "claim_data_setup_session" in SQL
    assert "claim_data_setup_sessions" in SQL
    assert SQL.count("security invoker") >= 2
    assert "current_setting('request.jwt.claim.role'" not in SQL
    assert "revoke all on function public.claim_data_setup_session(uuid)" in SQL
    assert "grant execute on function public.claim_data_setup_session(uuid) to service_role" in SQL
    assert "grant execute on function public.claim_data_setup_sessions(integer) to service_role" in SQL

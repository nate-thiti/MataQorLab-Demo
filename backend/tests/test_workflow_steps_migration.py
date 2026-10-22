from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "workflow_steps.sql"
).read_text(encoding="utf-8").lower()


def test_workflow_steps_table_belongs_to_data_setup_sessions():
    assert "create table if not exists public.workflow_steps" in SQL
    assert "references public.data_setup_sessions(id)" in SQL
    assert "on delete cascade" in SQL


def test_workflow_steps_status_and_type_constraints():
    for step in ("inspect", "prepare", "map", "validate", "clean", "finalize"):
        assert f"'{step}'" in SQL
    for status in (
        "pending", "ready", "running", "awaiting_user",
        "completed", "failed", "skipped", "stale", "superseded",
    ):
        assert f"'{status}'" in SQL
    assert "version integer not null default 1" in SQL
    assert "attempt integer not null default 1" in SQL


def test_workflow_steps_indexes_and_history_uniqueness():
    assert "idx_workflow_steps_session_type_version_attempt" in SQL
    assert "idx_workflow_steps_session_updated" in SQL
    assert "idx_workflow_steps_session_status" in SQL
    assert "idx_workflow_steps_session_type" in SQL


def test_workflow_steps_rls_is_owner_scoped_via_session():
    assert "enable row level security" in SQL
    assert "users read own workflow steps" in SQL
    assert "session.user_id = (select auth.uid())" in SQL
    assert "revoke all on public.workflow_steps from public, anon, authenticated" in SQL
    assert "grant select on public.workflow_steps to authenticated" in SQL
    assert "grant all on public.workflow_steps to service_role" in SQL


def test_begin_workflow_step_rpc_is_service_role_only():
    assert "create or replace function public.begin_workflow_step" in SQL
    assert "for update" in SQL
    assert "revoke all on function public.begin_workflow_step" in SQL
    assert "grant execute on function public.begin_workflow_step" in SQL
    assert "to service_role" in SQL
    assert "current_setting('request.jwt.claim.role'" not in SQL


def test_session_summary_columns_are_additive():
    assert "add column if not exists next_action" in SQL
    assert "add column if not exists last_failed_step" in SQL

from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "p1_dashboard_reliability.sql"
).read_text(encoding="utf-8").lower()


def test_visualization_proposals_are_idempotent_and_filters_persist():
    assert "add column if not exists source_message_id uuid" in SQL
    assert "idx_visualization_reports_source_message" in SQL
    assert "add column if not exists filter_state jsonb" in SQL


def test_share_view_sessions_are_backend_only():
    assert "create table if not exists public.visualization_share_view_sessions" in SQL
    assert "primary key (share_id, view_session_id)" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL

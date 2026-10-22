from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "p2_enterprise_governance.sql"
).read_text(encoding="utf-8").lower()


def test_workspace_ownership_columns_cover_product_spine():
    for table in (
        "dataset_catalog",
        "dataset_versions",
        "data_setup_sessions",
        "visualization_reports",
        "semantic_metric_definitions",
    ):
        assert f"alter table public.{table}" in SQL
        assert "add column if not exists organization_id" in SQL
        assert "add column if not exists workspace_id" in SQL


def test_resource_grants_and_approver_fields_exist():
    assert "create table if not exists public.resource_grants" in SQL
    assert "principal_type text not null" in SQL
    assert "add column if not exists approved_by" in SQL
    assert "add column if not exists approved_at" in SQL


def test_immutable_audit_and_dlq_are_service_backed():
    assert "create table if not exists public.platform_audit_events" in SQL
    assert "create table if not exists public.admin_access_events" in SQL
    assert "create table if not exists public.job_dead_letters" in SQL
    assert "no browser access to admin audit" in SQL
    assert "no browser access to job dead letters" in SQL
    assert "to service_role" in SQL

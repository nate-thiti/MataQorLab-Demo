from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "p1_unified_dataset_catalog.sql"
).read_text(encoding="utf-8").lower()


def test_catalog_migration_creates_immutable_versions_and_lineage():
    assert "create table if not exists public.dataset_catalog" in SQL
    assert "create table if not exists public.dataset_versions" in SQL
    assert "create table if not exists public.dataset_lineage_events" in SQL
    assert "unique (catalog_id, version_number)" in SQL
    assert "idx_dataset_versions_run" in SQL
    assert "materialized_prepared boolean not null default true" in SQL


def test_catalog_registration_is_atomic_and_service_role_only():
    assert "create or replace function public.register_dataset_version" in SQL
    assert "for update" in SQL
    assert "security invoker" in SQL
    assert "set search_path = ''" in SQL
    assert "to service_role" in SQL
    assert "from public, anon, authenticated" in SQL


def test_cloud_joins_the_shared_setup_source_contract():
    assert "check (source_type in ('file', 'api', 'sql', 'cloud'))" in SQL
    assert "add column if not exists dataset_version_id uuid" in SQL

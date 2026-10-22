from unittest.mock import MagicMock

from app.services.dataset_loader import load_handle_from_storage


def test_stable_etl_identity_resolves_latest_version_and_busts_cache(monkeypatch):
    client = MagicMock()
    schedules = MagicMock()
    schedules.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "latest_output_file": "etl_dataset_current.parquet",
            "latest_output_version": "etl_sales_v20260724.parquet",
        }
    ]
    client.table.return_value = schedules
    cached_handle = MagicMock()
    cached_handle.row_count.return_value = 42
    cache_lookup = MagicMock(return_value=cached_handle)

    monkeypatch.setattr(
        "app.services.dataset_loader.get_supabase_client",
        lambda: client,
    )
    monkeypatch.setattr(
        "app.services.dataset_loader.lookup_storage_size",
        lambda _user_id, _file_name: 2048,
    )
    monkeypatch.setattr(
        "app.services.dataset_loader.get_storage_object_metadata",
        lambda _bucket, _path: {"size": 2048, "updated_at": "2026-07-24T00:00:00Z"},
    )
    monkeypatch.setattr(
        "app.services.dataset_loader.try_load_cached_handle",
        cache_lookup,
    )
    monkeypatch.setattr(
        "app.services.dataset_loader.validate_upload_bytes",
        lambda *_args: None,
    )

    result = load_handle_from_storage("user-1", "etl:schedule-1")

    assert result is cached_handle
    cache_lookup.assert_called_once_with(
        "user-1",
        "etl:schedule-1@etl_sales_v20260724.parquet",
        2048,
        "etl:schedule-1@etl_sales_v20260724.parquet|2048|2026-07-24T00:00:00Z",
    )

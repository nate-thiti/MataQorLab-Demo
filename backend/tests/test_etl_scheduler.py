from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.etl_execution import EtlExecutionError
from app.services.etl_execution import (
    build_output_dataset_key,
    build_output_file_names,
)
from app.services.etl_scheduler import (
    _finish_schedule,
    claim_due_schedules,
    run_schedule_now,
)


def test_claim_due_schedules_uses_bounded_worker_settings():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [{"id": "schedule-1"}]

    result = claim_due_schedules(client, "worker-1")

    assert result == [{"id": "schedule-1"}]
    client.rpc.assert_called_once_with(
        "claim_due_etl_schedules",
        {
            "p_worker_id": "worker-1",
            "p_limit": settings.ETL_SCHEDULER_BATCH_SIZE,
            "p_lease_seconds": settings.ETL_SCHEDULER_LEASE_SECONDS,
        },
    )


def test_run_now_rejects_an_already_leased_schedule():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = []

    with pytest.raises(EtlExecutionError, match="already running"):
        run_schedule_now("schedule-1", client=client, worker_id="worker-1")


def test_finish_schedule_releases_lease_and_records_run():
    client = MagicMock()
    schedule = {
        "id": "schedule-1",
        "schedule_kind": "manual",
        "timezone": "UTC",
        "enabled": True,
        "consecutive_failures": 3,
    }

    _finish_schedule(
        client,
        schedule,
        "worker-1",
        result={
            "run_id": "run-1",
            "output_file": "etl_dataset_current.parquet",
            "output_version": "etl_sales_v1.parquet",
        },
    )

    payload = client.table.return_value.update.call_args.args[0]
    assert payload["last_status"] == "completed"
    assert payload["last_run_id"] == "run-1"
    assert payload["latest_output_file"] == "etl_dataset_current.parquet"
    assert payload["latest_output_version"] == "etl_sales_v1.parquet"
    assert payload["consecutive_failures"] == 0
    assert payload["locked_at"] is None
    assert payload["locked_by"] is None


def test_schedule_output_identity_is_stable_while_versions_change():
    dataset_key = build_output_dataset_key("schedule-1")
    first_current, first_version = build_output_file_names(
        dataset_key,
        "Daily sales",
        "sales.csv",
        "20260724T010000Z",
    )
    next_current, next_version = build_output_file_names(
        dataset_key,
        "Daily sales",
        "sales.csv",
        "20260725T010000Z",
    )

    assert dataset_key == "etl:schedule-1"
    assert first_current == next_current
    assert first_version != next_version
    assert first_current.endswith(".parquet")

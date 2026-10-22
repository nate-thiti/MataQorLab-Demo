import pytest

from app.services.dataset_catalog import (
    canonical_dataset_key,
    register_completed_dataset_version,
)


class RpcResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.name = None
        self.params = None

    def rpc(self, name, params):
        self.name = name
        self.params = params
        return RpcResult(self.data)


def test_canonical_dataset_key_is_stable_across_source_types():
    assert canonical_dataset_key("file", {"file_name": "sales.csv"}) == "file:sales.csv"
    assert canonical_dataset_key(
        "api", {"connection_id": "api-1"}
    ) == "api:api-1"
    assert canonical_dataset_key(
        "sql", {"connection_id": "db-1", "table_name": "orders"}
    ) == "sql:db-1:orders"
    assert canonical_dataset_key(
        "cloud", {"connection_id": "cloud-1"}
    ) == "cloud:cloud-1"


def test_canonical_dataset_key_rejects_missing_or_unsupported_sources():
    with pytest.raises(ValueError, match="Unsupported"):
        canonical_dataset_key("stream", {"connection_id": "x"})
    with pytest.raises(ValueError, match="identity"):
        canonical_dataset_key("api", {})


def test_register_completed_version_uses_atomic_rpc():
    client = FakeClient([{"id": "version-1", "version_number": 2}])
    result = register_completed_dataset_version(
        client,
        user_id="user-1",
        source_type="sql",
        source_ref={"connection_id": "db-1", "table_name": "orders"},
        display_name="Orders",
        source_fingerprint="source-hash",
        recipe_hash="recipe-hash",
        contract_hash="contract-hash",
        recipe_id="recipe-1",
        run_id="run-1",
        data_setup_session_id="setup-1",
        output_dataset_key="etl:recipe:recipe-1",
        output_file="orders.parquet",
        output_version="orders_v2.parquet",
        lineage={"trigger_kind": "data_setup"},
    )

    assert result["id"] == "version-1"
    assert client.name == "register_dataset_version"
    assert client.params["p_canonical_dataset_key"] == "sql:db-1:orders"
    assert client.params["p_run_id"] == "run-1"
    assert client.params["p_lineage"]["trigger_kind"] == "data_setup"


def test_registration_tolerates_catalog_not_yet_migrated():
    class MissingMigrationClient:
        def rpc(self, _name, _params):
            raise RuntimeError("PGRST202 function not found in schema cache")

    assert register_completed_dataset_version(
        MissingMigrationClient(),
        user_id="user-1",
        source_type="file",
        source_ref={"file_name": "sales.csv"},
        display_name="Sales",
        source_fingerprint=None,
        recipe_hash=None,
        contract_hash=None,
        recipe_id=None,
        run_id=None,
        data_setup_session_id=None,
        output_dataset_key="etl:recipe:1",
        output_file="sales.parquet",
        output_version=None,
    ) is None

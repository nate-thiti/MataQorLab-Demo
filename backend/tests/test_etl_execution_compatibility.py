from types import SimpleNamespace

from app.services.etl_execution import _insert_pipeline_run


def test_data_setup_run_supports_legacy_trigger_kind_constraint():
    inserted = []

    class Query:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            inserted.append(self.payload)
            if self.payload["trigger_kind"] == "data_setup":
                raise RuntimeError("etl_pipeline_runs_trigger_kind_check")
            return SimpleNamespace(data=[{"id": "run-1", **self.payload}])

    class Client:
        def table(self, name):
            assert name == "etl_pipeline_runs"
            return self

        def insert(self, payload):
            return Query(payload)

    response = _insert_pipeline_run(Client(), {
        "trigger_kind": "data_setup",
        "recipe_snapshot": {"version": 1},
    })

    assert response.data[0]["trigger_kind"] == "manual"
    assert inserted[1]["recipe_snapshot"]["_requested_trigger_kind"] == "data_setup"

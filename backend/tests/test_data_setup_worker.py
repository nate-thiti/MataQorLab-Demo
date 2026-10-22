import asyncio
from types import SimpleNamespace

from app.services import data_setup_worker


def test_data_setup_worker_claims_and_processes_jobs(monkeypatch):
    processed = []

    async def immediate(func, *args):
        return func(*args)

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[{"id": "setup-1", "user_id": "user-1"}])

    class Client:
        def rpc(self, name, args):
            assert name == "claim_data_setup_sessions"
            assert args == {"p_limit": 2}
            return Rpc()

    monkeypatch.setattr(data_setup_worker, "get_supabase_client", lambda: Client())
    monkeypatch.setattr(data_setup_worker.asyncio, "to_thread", immediate)
    monkeypatch.setattr(
        data_setup_worker,
        "process_data_setup_session",
        lambda session_id, user_id: processed.append((session_id, user_id)),
    )

    claimed = asyncio.run(data_setup_worker.process_claimed_data_setup_batch(batch_size=2))

    assert claimed == 1
    assert processed == [("setup-1", "user-1")]


def test_data_setup_worker_supports_legacy_claim_rpc_with_opaque_secret_key(monkeypatch):
    processed = []
    rows = [{"id": "setup-1", "user_id": "user-1", "status": "approved"}]

    async def immediate(func, *args):
        return func(*args)

    class Rpc:
        def execute(self):
            raise RuntimeError("service_role required")

    class Query:
        def __init__(self):
            self.filters = {}
            self.payload = None

        def select(self, *_args):
            return self

        def update(self, payload):
            self.payload = payload
            return self

        def eq(self, key, value):
            self.filters[key] = value
            return self

        def order(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            matched = [
                row for row in rows
                if all(row.get(key) == value for key, value in self.filters.items())
            ]
            if self.payload:
                for row in matched:
                    row.update(self.payload)
            return SimpleNamespace(data=matched)

    class Client:
        def rpc(self, *_args):
            return Rpc()

        def table(self, name):
            assert name == "data_setup_sessions"
            return Query()

    monkeypatch.setattr(data_setup_worker, "get_supabase_client", lambda: Client())
    monkeypatch.setattr(data_setup_worker.asyncio, "to_thread", immediate)
    monkeypatch.setattr(
        data_setup_worker,
        "process_data_setup_session",
        lambda session_id, user_id: processed.append((session_id, user_id)),
    )

    claimed = asyncio.run(data_setup_worker.process_claimed_data_setup_batch(batch_size=2))

    assert claimed == 1
    assert rows[0]["status"] == "processing"
    assert processed == [("setup-1", "user-1")]

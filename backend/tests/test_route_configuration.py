import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes


def test_etl_schedule_route_has_backend_settings_available():
    assert routes.settings.ETL_MAX_SCHEDULES_PER_USER > 0


def test_list_etl_schedules_returns_configured_limit(monkeypatch):
    class Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        @property
        def not_(self):
            return self

        def is_(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class Client:
        def table(self, _name):
            return Query()

    monkeypatch.setattr(routes, "get_supabase_client", lambda: Client())

    payload = asyncio.run(routes.list_etl_schedules("user-1"))

    assert payload["schedules"] == []
    assert payload["schedule_limit"] == routes.settings.ETL_MAX_SCHEDULES_PER_USER


def test_trusted_conversation_id_accepts_only_owned_conversations(monkeypatch):
    class Query:
        def __init__(self, rows):
            self.rows = rows

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, column, value):
            self.rows = [row for row in self.rows if row.get(column) == value]
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=self.rows)

    class Client:
        def __init__(self, rows):
            self.rows = rows

        def table(self, _name):
            return Query(list(self.rows))

    monkeypatch.setattr(
        routes,
        "get_supabase_client",
        lambda: Client([{"id": "conversation-1", "user_id": "user-1"}]),
    )

    assert routes._trusted_conversation_id("user-1", "conversation-1") == "conversation-1"
    with pytest.raises(HTTPException) as exc:
        routes._trusted_conversation_id("user-2", "conversation-1")
    assert exc.value.status_code == 403


def test_data_setup_claim_falls_back_for_legacy_rpc_guard():
    updated = {}

    class Rpc:
        def execute(self):
            raise RuntimeError("service_role required")

    class Query:
        def update(self, payload):
            updated.update(payload)
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "setup-1", **updated}])

    class Client:
        def rpc(self, *_args):
            return Rpc()

        def table(self, name):
            assert name == "data_setup_sessions"
            return Query()

    claimed = routes._claim_data_setup_session(Client(), "setup-1", "user-1")

    assert claimed[0]["status"] == "processing"

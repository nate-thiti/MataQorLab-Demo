from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.ai_logic import PromptManager
from app.services import governed_memory
from app.services.governed_memory import GovernanceError, _slug


class _RowsQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _EnterpriseSeatClient:
    def __init__(self):
        self.membership_reads = 0

    def table(self, name):
        if name == "profiles":
            return _RowsQuery([{
                "subscription_seats": 2,
                "plans": {"name": "Enterprise"},
            }])
        if name == "organization_members":
            self.membership_reads += 1
            if self.membership_reads == 1:
                return _RowsQuery([{"user_id": "owner-1"}])
            return _RowsQuery([
                {"user_id": "owner-1", "status": "active"},
                {"user_id": "member-1", "status": "active"},
            ])
        raise AssertionError(f"Unexpected table: {name}")


def test_governed_memory_is_rendered_as_bounded_approved_context():
    block = PromptManager.format_persistent_chat_memory({
        "governed": {
            "items": [{
                "scope": "organization",
                "type": "kpi_formula",
                "title": "Recognized revenue",
                "content": "Exclude cancelled orders.",
                "confidence": 1,
                "source_hash": "abc",
            }]
        }
    })
    assert "Approved governed context" in block
    assert "Exclude cancelled orders." in block
    assert "never override current computed evidence" in block


def test_slug_is_lowercase_and_bounded():
    assert _slug("Finance & Operations") == "finance-operations"
    assert len(_slug("x" * 1000)) <= 63


def test_tenancy_migration_has_rls_grants_and_cross_tenant_workspace_constraint():
    sql = (
        Path(__file__).parents[1]
        / "supabase"
        / "organization_workspace_memory.sql"
    ).read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "private.is_organization_member" in sql
    assert "FOREIGN KEY (workspace_id, organization_id)" in sql
    assert "REVOKE ALL ON TABLE" in sql
    assert "TO authenticated" in sql


def test_company_member_can_only_edit_records_they_created(monkeypatch):
    monkeypatch.setattr(
        governed_memory, "_organization_role", lambda *_args: "member"
    )
    own = {
        "scope": "organization",
        "organization_id": "org-1",
        "created_by": "user-1",
    }
    other = {**own, "created_by": "user-2"}

    assert governed_memory._can_edit_memory(object(), "user-1", own)
    assert not governed_memory._can_edit_memory(object(), "user-1", other)


def test_workspace_viewer_cannot_edit_governed_memory(monkeypatch):
    monkeypatch.setattr(
        governed_memory, "_organization_role", lambda *_args: "admin"
    )
    monkeypatch.setattr(
        governed_memory, "_workspace_role", lambda *_args: "viewer"
    )
    memory = {
        "scope": "workspace",
        "organization_id": "org-1",
        "workspace_id": "workspace-1",
        "created_by": "user-1",
    }

    assert not governed_memory._can_edit_memory(object(), "user-1", memory)


def test_create_organization_requires_enterprise_plan(monkeypatch):
    class _Client:
        def table(self, name):
            assert name == "profiles"
            return _RowsQuery([{
                "plans": {"name": "Pro"},
            }])

    with pytest.raises(GovernanceError, match="Enterprise"):
        governed_memory.create_organization("user-1", "Acme", client=_Client())


def test_only_owner_can_delete_organization(monkeypatch):
    monkeypatch.setattr(governed_memory, "_organization_role", lambda *_args: "admin")
    with pytest.raises(GovernanceError, match="owner"):
        governed_memory.delete_organization("admin-1", "org-1", client=object())


def test_update_organization_requires_admin_role(monkeypatch):
    calls = {}

    class _Client:
        def table(self, name):
            assert name == "organizations"

            class _Update:
                def update(self, payload):
                    calls["payload"] = payload
                    return self

                def eq(self, *_args, **_kwargs):
                    return self

                def execute(self):
                    return SimpleNamespace(data=[{"id": "org-1", "name": calls["payload"]["name"]}])

            return _Update()

    monkeypatch.setattr(
        governed_memory, "_require_org_role", lambda *_args, **_kwargs: "admin"
    )
    updated = governed_memory.update_organization(
        "admin-1", "org-1", "  Renamed Org  ", client=_Client()
    )
    assert updated["name"] == "Renamed Org"
    assert "updated_at" in calls["payload"]


def test_delete_workspace_requires_org_admin(monkeypatch):
    class _Client:
        def table(self, name):
            assert name == "workspaces"

            class _Query:
                def select(self, *_args, **_kwargs):
                    return self

                def eq(self, *_args, **_kwargs):
                    return self

                def limit(self, *_args, **_kwargs):
                    return self

                def delete(self):
                    return self

                def execute(self):
                    return SimpleNamespace(
                        data=[{
                            "id": "ws-1",
                            "organization_id": "org-1",
                            "name": "Finance",
                        }]
                    )

            return _Query()

    monkeypatch.setattr(
        governed_memory, "_require_org_role", lambda *_args, **_kwargs: "owner"
    )
    result = governed_memory.delete_workspace("owner-1", "ws-1", client=_Client())
    assert result == {
        "id": "ws-1",
        "organization_id": "org-1",
        "deleted": True,
        "name": "Finance",
    }


def test_enterprise_organization_cannot_exceed_paid_seats():
    with pytest.raises(GovernanceError) as exc:
        governed_memory._enforce_organization_seat_limit(
            _EnterpriseSeatClient(),
            "org-1",
            "member-2",
        )
    assert "seat limit reached" in str(exc.value)

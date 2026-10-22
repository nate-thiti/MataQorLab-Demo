from unittest.mock import MagicMock

import pytest

from app.services.job_dlq import enqueue_dead_letter, mark_dead_letter
from app.services.platform_audit import record_platform_audit
from app.services.sli import sli_event
from app.services.tenancy import (
    TenancyError,
    can_access_owner_or_workspace,
    grant_resource_access,
    require_workspace_access,
)


def test_workspace_write_requires_editor_role():
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "role": "viewer",
            "workspaces": {"id": "ws-1", "organization_id": "org-1"},
        }
    ]

    with pytest.raises(TenancyError, match="write access"):
        require_workspace_access(
            client,
            user_id="user-1",
            workspace_id="ws-1",
            write=True,
        )


def test_owner_or_workspace_membership_controls_access():
    assert can_access_owner_or_workspace(
        row={"user_id": "user-1"},
        user_id="user-1",
    )
    assert can_access_owner_or_workspace(
        row={"user_id": "other", "workspace_id": "ws-1"},
        user_id="user-2",
        workspace_ids={"ws-1"},
    )
    assert not can_access_owner_or_workspace(
        row={"user_id": "other", "workspace_id": "ws-2"},
        user_id="user-2",
        workspace_ids={"ws-1"},
    )


def test_resource_grant_upserts_without_duplicate_rows():
    client = MagicMock()
    grants = MagicMock()
    grants.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    grants.insert.return_value.execute.return_value.data = [{
        "id": "grant-1",
        "resource_type": "dataset",
        "role": "viewer",
    }]
    client.table.return_value = grants

    grant = grant_resource_access(
        client,
        organization_id="org-1",
        workspace_id="ws-1",
        resource_type="dataset",
        resource_id="dataset-1",
        principal_type="workspace",
        principal_id="ws-2",
        role="viewer",
        granted_by="admin-1",
    )

    assert grant["id"] == "grant-1"
    grants.insert.assert_called_once()


def test_platform_audit_and_dlq_tolerate_missing_migration():
    client = MagicMock()
    table = MagicMock()
    table.insert.return_value.execute.side_effect = Exception("PGRST205")
    table.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception(
        "PGRST205"
    )
    client.table.return_value = table

    assert record_platform_audit(
        client,
        actor_user_id="user-1",
        action="dataset.shared",
        resource_type="dataset",
        resource_id="d1",
    ) is None
    assert enqueue_dead_letter(
        client,
        job_kind="data_setup",
        job_key="session-1",
        error_message="boom",
    ) is None


def test_dead_letter_status_transitions():
    client = MagicMock()
    client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{
        "id": "dlq-1",
        "status": "resolved",
    }]

    row = mark_dead_letter(client, dead_letter_id="dlq-1", status="resolved")
    assert row["status"] == "resolved"


def test_sli_event_marks_budget_breach():
    event = sli_event("dashboard", duration_ms=5000, outcome="ok")
    assert event["within_slo"] is False
    assert event["slo_target_ms"] == 4000
    assert sli_event("chat_ttfb", duration_ms=1200)["within_slo"] is True

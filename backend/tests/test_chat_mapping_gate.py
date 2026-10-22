import pytest
from fastapi import HTTPException

from app.api.routes import _require_user_approved_mapping
from app.schemas.chat import ChatRequest


def _request(**overrides):
    payload = {
        "messages": [{"role": "user", "content": "analyze"}],
        "user_id": "00000000-0000-0000-0000-000000000001",
    }
    payload.update(overrides)
    return ChatRequest(**payload)


@pytest.mark.parametrize(
    "source",
    [
        {"file_attachment_name": "sales.xlsx"},
        {"connection_id": "api-1", "connection_type": "api"},
    ],
)
def test_mapping_gate_blocks_first_unmapped_file_or_api_request(source):
    with pytest.raises(HTTPException) as exc:
        _require_user_approved_mapping(_request(**source))
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "source",
    [
        {"file_attachment_name": "sales.xlsx"},
        {"connection_id": "api-1", "connection_type": "api"},
    ],
)
def test_mapping_gate_allows_confirmed_mapping(source):
    _require_user_approved_mapping(
        _request(
            **source,
            column_mapping={"net_sales": "revenue"},
            data_setup_session_id="00000000-0000-0000-0000-000000000010",
        )
    )


def test_mapping_gate_rejects_recipe_without_ready_setup_identity():
    with pytest.raises(HTTPException):
        _require_user_approved_mapping(
            _request(
                file_attachment_name="sales.xlsx",
                cleaning_recipe={"apply": True, "rules": {"dedupe": True}},
            )
        )


def test_mapping_gate_requires_setup_for_sql_but_allows_agent_resume():
    with pytest.raises(HTTPException):
        _require_user_approved_mapping(
            _request(connection_id="db-1", connection_type="sql")
        )
    _require_user_approved_mapping(
        _request(
            connection_id="db-1",
            connection_type="sql",
            column_mapping={"amount": "sales"},
            data_setup_session_id="00000000-0000-0000-0000-000000000010",
        )
    )
    _require_user_approved_mapping(
        _request(
            file_attachment_name="sales.xlsx",
            agent_session_id="00000000-0000-0000-0000-000000000002",
        )
    )

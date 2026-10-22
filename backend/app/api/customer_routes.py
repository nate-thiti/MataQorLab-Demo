"""Authenticated customer experience APIs."""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.customer_experience import (
    CustomerExperienceError,
    create_alert_rule,
    create_collaboration_item,
    create_embed_config,
    create_lineage_record,
    create_organization_invitation,
    accept_organization_invitation,
    get_customer_experience_overview,
    save_onboarding_progress,
    update_alert_rule,
    update_collaboration_status,
    upsert_data_asset,
    upsert_integration,
)
from app.services.smart_alert_scheduler import SmartAlertError, run_alert_rule_now

router = APIRouter()


class OnboardingProgressRequest(BaseModel):
    completed_steps: list[str] = Field(default_factory=list, max_length=8)
    dismissed: bool = False
    sample_dataset_loaded: bool = False
    first_dashboard_id: str | None = None


class DataAssetRequest(BaseModel):
    asset_kind: Literal["file", "api", "sql", "cloud", "dataset"]
    asset_key: str = Field(min_length=1, max_length=500)
    display_name: str = Field(min_length=1, max_length=240)
    organization_id: str | None = None
    workspace_id: str | None = None
    connection_status: Literal["unknown", "healthy", "degraded", "failed", "paused"] = "unknown"
    freshness_status: Literal["unknown", "fresh", "stale", "expired"] = "unknown"
    quality_score: float | None = Field(default=None, ge=0, le=100)
    schema_hash: str | None = Field(default=None, max_length=256)
    row_count: int | None = Field(default=None, ge=0)
    issue_count: int = Field(default=0, ge=0)
    issues: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = Field(default=None, max_length=2000)


class LineageRequest(BaseModel):
    dataset_key: str = Field(min_length=1, max_length=500)
    organization_id: str | None = None
    workspace_id: str | None = None
    report_id: str | None = None
    finding_hash: str | None = Field(default=None, max_length=256)
    metric_key: str | None = Field(default=None, max_length=160)
    formula: str | None = Field(default=None, max_length=5000)
    executed_sql: str | None = Field(default=None, max_length=20000)
    source_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    filter_state: dict[str, Any] = Field(default_factory=dict)
    data_version: str | None = Field(default=None, max_length=256)
    confidence: float = Field(default=1, ge=0, le=1)
    computed_at: str | None = None


class CollaborationRequest(BaseModel):
    report_id: str
    organization_id: str | None = None
    workspace_id: str | None = None
    item_kind: Literal["comment", "annotation", "assignment", "approval"] = "comment"
    body: str = Field(default="", max_length=5000)
    anchor: dict[str, Any] = Field(default_factory=dict)
    assignee_user_id: str | None = None


class CollaborationStatusRequest(BaseModel):
    status: Literal["open", "resolved", "approved", "rejected"]


class AlertRuleRequest(BaseModel):
    organization_id: str | None = None
    workspace_id: str | None = None
    report_id: str
    name: str = Field(min_length=1, max_length=160)
    metric_key: str = Field(min_length=1, max_length=160)
    operator: Literal["gt", "gte", "lt", "lte", "eq", "change_gt", "change_lt"]
    threshold: float | None = None
    channels: list[Literal["in_app", "email", "slack", "teams", "webhook"]] = Field(
        default_factory=lambda: ["in_app"],
        min_length=1,
        max_length=5,
    )
    recipients: list[str] = Field(default_factory=list, max_length=100)
    cooldown_minutes: int = Field(default=60, ge=1, le=43200)
    evaluation_interval_minutes: int = Field(default=5, ge=1, le=1440)
    filter_state: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    muted_until: str | None = None


class IntegrationRequest(BaseModel):
    organization_id: str | None = None
    integration_kind: Literal["connector", "notification", "sso", "scim", "embed"]
    provider: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    status: Literal["draft", "ready", "active", "error", "disabled"] = "draft"
    enabled: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)
    last_tested_at: str | None = None
    last_error: str | None = Field(default=None, max_length=2000)


class OrganizationInvitationRequest(BaseModel):
    organization_id: str
    workspace_id: str | None = None
    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "reviewer", "member"] = "member"
    expires_in_days: int = Field(default=7, ge=1, le=30)


class OrganizationInvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=32, max_length=500)


class EmbedConfigRequest(BaseModel):
    organization_id: str | None = None
    report_id: str
    allowed_origins: list[str] = Field(min_length=1, max_length=20)
    branding: dict[str, Any] = Field(default_factory=dict)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


def _run(operation, *args):
    try:
        return operation(*args)
    except CustomerExperienceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/overview")
async def customer_experience_overview(
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _run(get_customer_experience_overview, user_id)


@router.put("/onboarding")
async def customer_onboarding_update(
    body: OnboardingProgressRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {"onboarding": _run(save_onboarding_progress, user_id, body.model_dump())}


@router.put("/data-assets")
async def customer_data_asset_update(
    body: DataAssetRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {"asset": _run(upsert_data_asset, user_id, body.model_dump())}


@router.post("/lineage")
async def customer_lineage_create(
    body: LineageRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {"lineage": _run(create_lineage_record, user_id, body.model_dump())}


@router.post("/collaboration")
async def customer_collaboration_create(
    body: CollaborationRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {
        "item": _run(create_collaboration_item, user_id, body.model_dump())
    }


@router.patch("/collaboration/{item_id}")
async def customer_collaboration_update(
    item_id: str,
    body: CollaborationStatusRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {
        "item": _run(update_collaboration_status, user_id, item_id, body.status)
    }


@router.post("/alerts")
async def customer_alert_create(
    body: AlertRuleRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {"alert": _run(create_alert_rule, user_id, body.model_dump())}


@router.patch("/alerts/{rule_id}")
async def customer_alert_update(
    rule_id: str,
    body: AlertRuleUpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {
        "alert": _run(
            update_alert_rule,
            user_id,
            rule_id,
            body.model_dump(exclude_unset=True),
        )
    }


@router.post("/alerts/{rule_id}/evaluate")
async def customer_alert_evaluate_now(
    rule_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    try:
        return {"evaluation": run_alert_rule_now(user_id, rule_id)}
    except SmartAlertError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/integrations")
async def customer_integration_update(
    body: IntegrationRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {
        "integration": _run(upsert_integration, user_id, body.model_dump())
    }


@router.post("/organization-invitations")
async def customer_organization_invitation_create(
    body: OrganizationInvitationRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _run(create_organization_invitation, user_id, body.model_dump())


@router.post("/organization-invitations/accept")
async def customer_organization_invitation_accept(
    body: OrganizationInvitationAcceptRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return {
        "invitation": _run(
            accept_organization_invitation,
            user_id,
            body.token,
        )
    }


@router.post("/embeds")
async def customer_embed_create(
    body: EmbedConfigRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return _run(create_embed_config, user_id, body.model_dump())

# pyrefly: ignore [missing-import]
from typing import Annotated, Any, Dict, List, Literal, Mapping, Optional
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
import json
import numpy as np
import pandas as pd

from app.core.auth import get_current_user_id, require_matching_user_id
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import chat_service
from app.services.quota_service import (
    check_user_message_quota,
    get_user_tier,
    record_token_usage,
)
from app.services.dataset_loader import DatasetLoadError, load_handle_from_storage
from app.services.analytics_service import calculate_analytics_for_handle
from app.core.excel_report import generate_excel_report
from app.services.file_validation import FileValidationError, validate_upload_bytes
from app.core.supabase import get_supabase_client
from app.services.external_api import fetch_from_connection
from app.services.semantic_metrics import (
    delete_custom_metric,
    fetch_custom_metrics,
    upsert_custom_metric,
)
from app.services.semantic_mapping_gate import (
    evaluate_semantic_mapping_gate,
    normalize_mapping,
    scan_columns,
    suggested_mapping_from_scan,
)
from app.services.storage_quota import (
    StorageQuotaExceeded,
    enforce_customer_storage_quota,
    get_customer_storage_usage,
)

router = APIRouter()
logger = logging.getLogger("mataqorlab.api")

class ExcelReportRequest(BaseModel):
    file_attachment_name: str
    column_mapping: Optional[Dict[str, str]] = None
    title: str
    summary: str
    user_id: str
    locale: Optional[str] = "th"
    cleaning_profile: Optional[str] = "standard"


class VisualizationChartPayload(BaseModel):
    chart_type: str
    title: Optional[str] = None
    subtitle: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    data: List[Dict[str, Any]]
    insight: Optional[str] = None


class VisualizationReportCreateRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    executive_summary: Optional[str] = None
    dataset_key: Optional[str] = None
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    created_via: str = "workspace"
    status: str = "draft"
    chart: Optional[VisualizationChartPayload] = None
    dashboard_spec: Dict[str, Any] = Field(default_factory=dict)
    source_config: Dict[str, Any] = Field(default_factory=dict)
    pin: Optional[Dict[str, Any]] = None


class VisualizationReportUpdateRequest(BaseModel):
    user_id: str
    report_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    executive_summary: Optional[str] = None
    status: Optional[str] = None
    filter_state: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    pin: Optional[Dict[str, Any]] = None
    insight_action: Optional[Dict[str, Any]] = None
    decision_packet: Optional[Dict[str, Any]] = None


class VisualizationDecisionReproveRequest(BaseModel):
    user_id: str
    report_id: str
    filters: Dict[str, Any] = Field(default_factory=dict)


class VisualizationDashboardGenerateRequest(BaseModel):
    user_id: str
    report_id: str
    force: bool = False
    filters: Dict[str, Any] = Field(default_factory=dict)
    dashboard_spec: Optional[Dict[str, Any]] = None
    persist: bool = True


class VisualizationReportDuplicateRequest(BaseModel):
    user_id: str
    report_id: str
    title: Optional[str] = None


class VisualizationDashboardPlanRequest(BaseModel):
    user_id: str
    report_id: str
    instruction: str = Field(min_length=1, max_length=1000)
    current_spec: Optional[Dict[str, Any]] = None


class VisualizationRevisionRestoreRequest(BaseModel):
    user_id: str
    report_id: str
    revision_id: str


class VisualizationShareCreateRequest(BaseModel):
    user_id: str
    report_id: str
    expires_in_days: int = Field(default=30, ge=1, le=365)
    allow_detail_rows: bool = False
    max_views: Optional[int] = Field(default=None, ge=1, le=1_000_000)


class VisualizationShareRevokeRequest(BaseModel):
    user_id: str
    report_id: str
    share_id: str


class SharedVisualizationFilterRequest(BaseModel):
    filters: Dict[str, Any] = Field(default_factory=dict)


class VisualizationTemplateCreateRequest(BaseModel):
    user_id: str
    report_id: str
    name: str = Field(min_length=1, max_length=160)


class VisualizationTemplatePreviewRequest(BaseModel):
    user_id: str
    report_id: str
    template_id: str
    persist: bool = False


class VisualizationTemplateDeleteRequest(BaseModel):
    user_id: str
    template_id: str


class VisualizationChartCreateRequest(BaseModel):
    user_id: str
    report_id: str
    source_message_id: Optional[str] = None
    chart: VisualizationChartPayload


class VisualizationDeleteRequest(BaseModel):
    user_id: str
    report_id: Optional[str] = None
    chart_id: Optional[str] = None


class ValidateUploadRequest(BaseModel):
    file_name: str
    size_bytes: int


class WarmIngestCacheRequest(BaseModel):
    user_id: str
    file_name: str
    size_bytes: Optional[int] = None


class JsonMappingPreviewRequest(BaseModel):
    user_id: str
    file_name: str
    json_path: Optional[str] = None
    max_rows: int = 10


class EtlPreviewRequest(BaseModel):
    user_id: str
    file_name: str
    column_mapping: Optional[Dict[str, str]] = None
    cleaning_profile: Optional[str] = "standard"
    recipe: Optional[Dict[str, Any]] = None


class DataSetupScanRequest(BaseModel):
    user_id: str
    source_type: Literal["file", "api", "sql", "cloud"]
    file_name: Optional[str] = Field(default=None, max_length=500)
    connection_id: Optional[str] = Field(default=None, max_length=100)
    table_name: Optional[str] = Field(default=None, max_length=300)
    conversation_id: Optional[str] = None
    original_prompt: str = Field(default="", max_length=4000)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list, max_length=200)
    row_count_estimate: Optional[int] = Field(default=None, ge=0)
    row_count_exact: bool = False
    reuse_existing: bool = Field(
        default=False,
        description="Reuse/resume an active setup for the same source fingerprint (same user).",
    )


class DataSetupDraftRequest(BaseModel):
    user_id: str
    current_step: Literal[
        "scan", "structure", "mapping", "cleaning", "business_context", "review"
    ]
    answers: Dict[str, Any] = Field(default_factory=dict)
    column_mapping: Dict[str, str] = Field(default_factory=dict)
    cleaning_profile: Literal["standard", "financial", "conservative", "aggressive"] = "standard"
    cleaning_recipe: Dict[str, Any] = Field(default_factory=dict)
    business_context: Dict[str, Any] = Field(default_factory=dict)


class DataSetupPreviewRequest(DataSetupDraftRequest):
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list, max_length=200)


class DataSetupApproveRequest(DataSetupDraftRequest):
    pass


class DataSetupCancelRequest(BaseModel):
    user_id: str


class EtlRecipeRequest(BaseModel):
    user_id: str
    dataset_key: str
    name: str
    recipe: Dict[str, Any]
    recipe_id: Optional[str] = None


class EtlRecipeDeleteRequest(BaseModel):
    user_id: str
    recipe_id: str


class EtlScheduleRequest(BaseModel):
    user_id: str
    recipe_id: str
    schedule_kind: str = "manual"
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    output_name: Optional[str] = None
    incremental_column: Optional[str] = None
    alert_config: Optional[Dict[str, Any]] = None
    enabled: bool = True
    schedule_id: Optional[str] = None
    chat_delivery_enabled: bool = False
    chat_delivery_weekday: Optional[int] = Field(default=None, ge=1, le=7)
    chat_delivery_hour: int = Field(default=9, ge=0, le=23)
    chat_delivery_minute: int = Field(default=0, ge=0, le=59)
    chat_target_conversation_id: Optional[str] = None
    chat_delivery_prompt: Optional[str] = Field(default=None, max_length=1000)


class EtlScheduleDeleteRequest(BaseModel):
    user_id: str
    schedule_id: str


class EtlScheduleActionRequest(BaseModel):
    user_id: str
    schedule_id: str


class EtlSchedulePreviewRequest(BaseModel):
    user_id: str
    recipe_id: str
    alert_config: Optional[Dict[str, Any]] = None
    schedule_id: Optional[str] = None
    chat_delivery_enabled: bool = False
    chat_target_conversation_id: Optional[str] = None


class EtlRunRequest(BaseModel):
    user_id: str
    recipe_id: str
    output_name: Optional[str] = None


class ChatAnalysisPreferencesRequest(BaseModel):
    language: Optional[str] = Field(default=None, max_length=16)
    answer_style: Optional[str] = Field(default=None, max_length=32)
    currency: Optional[str] = Field(default=None, max_length=8)


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class OrganizationUpdateRequest(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=160)


class OrganizationDeleteRequest(BaseModel):
    organization_id: str


class WorkspaceCreateRequest(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=160)


class WorkspaceUpdateRequest(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=160)


class WorkspaceDeleteRequest(BaseModel):
    workspace_id: str


class GovernanceMemberRequest(BaseModel):
    organization_id: str
    member_user_id: str
    role: Literal["admin", "reviewer", "member"] = "member"
    workspace_id: Optional[str] = None


class ResourceGrantRequest(BaseModel):
    organization_id: str
    workspace_id: Optional[str] = None
    resource_type: Literal[
        "dataset",
        "dataset_version",
        "data_setup_session",
        "visualization_report",
        "semantic_metric",
        "etl_recipe",
    ]
    resource_id: str
    principal_type: Literal["organization", "workspace", "user"]
    principal_id: str
    role: Literal["viewer", "editor", "admin"] = "viewer"


class ResourceGrantRevokeRequest(BaseModel):
    organization_id: str
    grant_id: str


class JobDeadLetterUpdateRequest(BaseModel):
    dead_letter_id: str
    status: Literal["open", "replaying", "resolved", "discarded"]


class GovernedMemorySaveRequest(BaseModel):
    id: Optional[str] = None
    scope: Literal["personal", "organization", "workspace", "project", "dataset"] = "personal"
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    memory_type: Literal[
        "preference", "business_definition", "kpi_formula", "terminology",
        "policy", "reporting_convention", "dataset_fact",
    ] = "business_definition"
    memory_key: Optional[str] = None
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=12000)
    structured_value: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1, ge=0, le=1)
    source_type: Literal["manual", "verified_finding", "import", "correction"] = "manual"
    source_ref: Optional[str] = None


class GovernedMemoryReviewRequest(BaseModel):
    memory_id: str
    decision: Literal["approve", "reject"]


class GovernedMemoryActionRequest(BaseModel):
    memory_id: str
    revision_id: Optional[str] = None


class CloudDatasetRequest(BaseModel):
    user_id: str
    provider: str
    display_name: str
    source_url: str
    sheet_name: Optional[str] = None
    json_path: Optional[str] = None
    recipe_id: Optional[str] = None


class CloudDatasetActionRequest(BaseModel):
    user_id: str
    connection_id: str
    force: bool = False


class SemanticMetricRequest(BaseModel):
    user_id: str
    dataset_key: str
    definition: Dict[str, Any]


class SemanticMetricDeleteRequest(BaseModel):
    user_id: str
    dataset_key: str
    metric_key: str


class DaxValidateRequest(BaseModel):
    user_id: str
    expression: str = Field(min_length=1, max_length=4000)
    columns: List[str] = Field(default_factory=list, max_length=500)
    mode: Literal["measure", "calculated_column"] = "measure"
    governed_relationships: bool = False


class DaxPreviewRequest(BaseModel):
    user_id: str
    dataset_key: str = Field(min_length=1, max_length=500)
    expression: str = Field(min_length=1, max_length=4000)
    name: str = Field(min_length=1, max_length=120)
    mode: Literal["measure", "calculated_column"] = "measure"
    governed_relationships: bool = False


class DaxPublishRequest(DaxPreviewRequest):
    approved_action_id: str = Field(min_length=1, max_length=200)
    label: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class PythonAnalysisProposalRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    dataset_key: str = Field(min_length=1, max_length=500)
    dataset_version_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    code: str = Field(min_length=1, max_length=100000)
    packages: List[str] = Field(default_factory=list, max_length=20)
    expected_outputs: List[str] = Field(default_factory=list, max_length=10)


class PythonAnalysisConfirmRequest(BaseModel):
    user_id: str
    approval_id: str = Field(min_length=1, max_length=200)


class PythonAnalysisCancelRequest(BaseModel):
    user_id: str


REPORT_SAMPLE_ROWS = 10_000


def _trusted_conversation_id(
    user_id: str, conversation_id: Optional[str]
) -> Optional[str]:
    """Reject cross-user conversation IDs before service-role memory/metrics writes."""
    if not conversation_id:
        return None
    response = (
        get_supabase_client()
        .table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation does not belong to the authenticated user",
        )
    return conversation_id


@router.post("/files/validate-upload")
@limiter.limit("60/minute")
async def validate_upload(
    request: Request,
    body: ValidateUploadRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = auth_user_id
    try:
        validate_upload_bytes(body.file_name, body.size_bytes)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "file_name": body.file_name}


@router.get("/files/storage-usage")
async def customer_storage_usage(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    return get_customer_storage_usage(auth_user_id)


@router.get("/files")
async def list_customer_files(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None, max_length=200),
):
    from app.services.storage_list import list_business_files

    return list_business_files(
        auth_user_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/datasets")
async def list_datasets(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workspace_id: Optional[str] = Query(default=None),
):
    from app.services.dataset_catalog import list_dataset_catalog

    return list_dataset_catalog(
        auth_user_id,
        limit=limit,
        offset=offset,
        workspace_id=workspace_id,
        client=get_supabase_client(),
    )


@router.get("/datasets/{catalog_id}/versions")
async def list_versions_for_dataset(
    catalog_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    from app.services.dataset_catalog import list_dataset_versions

    try:
        return list_dataset_versions(
            auth_user_id,
            catalog_id,
            limit=limit,
            offset=offset,
            client=get_supabase_client(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dataset-versions/{dataset_version_id}/lineage")
async def list_lineage_for_dataset_version(
    dataset_version_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=100, ge=1, le=200),
):
    from app.services.dataset_catalog import list_dataset_lineage

    try:
        return {
            "events": list_dataset_lineage(
                auth_user_id,
                dataset_version_id,
                limit=limit,
                client=get_supabase_client(),
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard/stats")
async def dashboard_stats(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.dashboard_stats import (
        DashboardStatsUnavailable,
        get_dashboard_stats,
    )

    try:
        return get_dashboard_stats(auth_user_id)
    except DashboardStatsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/chat/preferences")
async def get_chat_analysis_preferences(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.chat_intelligence import get_user_analysis_preferences
    return {"preferences": get_user_analysis_preferences(auth_user_id)}


@router.put("/chat/preferences")
@limiter.limit("30/minute")
async def put_chat_analysis_preferences(
    request: Request,
    body: ChatAnalysisPreferencesRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.chat_intelligence import save_user_analysis_preferences
    try:
        preferences = save_user_analysis_preferences(
            auth_user_id,
            body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"preferences": preferences}


@router.get("/governance/context")
async def governance_context(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import list_governance_context
    return list_governance_context(auth_user_id)


@router.post("/governance/organizations")
@limiter.limit("5/minute")
async def create_governance_organization(
    request: Request,
    body: OrganizationCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, create_organization
    try:
        return {"organization": create_organization(auth_user_id, body.name)}
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/governance/organizations")
@limiter.limit("20/minute")
async def update_governance_organization(
    request: Request,
    body: OrganizationUpdateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, update_organization
    try:
        return {
            "organization": update_organization(
                auth_user_id, body.organization_id, body.name
            )
        }
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/governance/organizations")
@limiter.limit("10/minute")
async def delete_governance_organization(
    request: Request,
    body: OrganizationDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, delete_organization
    try:
        return {"result": delete_organization(auth_user_id, body.organization_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/governance/workspaces")
@limiter.limit("10/minute")
async def create_governance_workspace(
    request: Request,
    body: WorkspaceCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, create_workspace
    try:
        return {"workspace": create_workspace(auth_user_id, body.organization_id, body.name)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/governance/workspaces")
@limiter.limit("20/minute")
async def update_governance_workspace(
    request: Request,
    body: WorkspaceUpdateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, update_workspace
    try:
        return {"workspace": update_workspace(auth_user_id, body.workspace_id, body.name)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/governance/workspaces")
@limiter.limit("10/minute")
async def delete_governance_workspace(
    request: Request,
    body: WorkspaceDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, delete_workspace
    try:
        return {"result": delete_workspace(auth_user_id, body.workspace_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/governance/members")
@limiter.limit("20/minute")
async def add_governance_member(
    request: Request,
    body: GovernanceMemberRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, add_member
    try:
        add_member(
            auth_user_id, body.organization_id, body.member_user_id, body.role,
            workspace_id=body.workspace_id,
        )
        return {"ok": True}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/governance/memories")
async def get_governed_memories(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    organization_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    from app.services.governed_memory import GovernanceError, list_memories
    try:
        return {"memories": list_memories(
            auth_user_id, organization_id=organization_id,
            workspace_id=workspace_id, status=status_filter,
        )}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/governance/memories")
@limiter.limit("30/minute")
async def upsert_governed_memory(
    request: Request,
    body: GovernedMemorySaveRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, save_memory
    try:
        return {"memory": save_memory(auth_user_id, body.model_dump())}
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/governance/memories/review")
@limiter.limit("30/minute")
async def review_governed_memory_route(
    request: Request,
    body: GovernedMemoryReviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, review_memory
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    try:
        return {"memory": review_memory(auth_user_id, body.memory_id, body.decision)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/governance/memories")
@limiter.limit("30/minute")
async def archive_governed_memory_route(
    request: Request,
    body: GovernedMemoryActionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, archive_memory
    try:
        return {"memory": archive_memory(auth_user_id, body.memory_id)}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/governance/memories/{memory_id}/history")
async def governed_memory_history(
    memory_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, memory_history
    try:
        return memory_history(auth_user_id, memory_id)
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/governance/memories/restore")
@limiter.limit("20/minute")
async def restore_governed_memory_route(
    request: Request,
    body: GovernedMemoryActionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.governed_memory import GovernanceError, restore_memory
    if not body.revision_id:
        raise HTTPException(status_code=400, detail="revision_id is required")
    try:
        return {"memory": restore_memory(
            auth_user_id, body.memory_id, body.revision_id,
        )}
    except GovernanceError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/governance/grants")
@limiter.limit("30/minute")
async def create_resource_grant(
    request: Request,
    body: ResourceGrantRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.platform_audit import record_platform_audit
    from app.services.tenancy import TenancyError, grant_resource_access

    _ = request
    client = get_supabase_client()
    membership = (
        client.table("organization_members")
        .select("role")
        .eq("organization_id", body.organization_id)
        .eq("user_id", auth_user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    role = (membership.data or [{}])[0].get("role")
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Organization admin required")
    try:
        grant = grant_resource_access(
            client,
            organization_id=body.organization_id,
            workspace_id=body.workspace_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            principal_type=body.principal_type,
            principal_id=body.principal_id,
            role=body.role,
            granted_by=auth_user_id,
        )
    except TenancyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_platform_audit(
        client,
        actor_user_id=auth_user_id,
        action="resource_grant.created",
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        organization_id=body.organization_id,
        workspace_id=body.workspace_id,
        detail={
            "grant_id": grant.get("id"),
            "principal_type": body.principal_type,
            "principal_id": body.principal_id,
            "role": body.role,
        },
    )
    return {"grant": grant}


@router.post("/governance/grants/revoke")
@limiter.limit("30/minute")
async def revoke_resource_grant(
    request: Request,
    body: ResourceGrantRevokeRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.platform_audit import record_platform_audit
    from app.services.tenancy import TenancyError, revoke_resource_access

    _ = request
    client = get_supabase_client()
    membership = (
        client.table("organization_members")
        .select("role")
        .eq("organization_id", body.organization_id)
        .eq("user_id", auth_user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if (membership.data or [{}])[0].get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Organization admin required")
    try:
        grant = revoke_resource_access(
            client,
            grant_id=body.grant_id,
            organization_id=body.organization_id,
        )
    except TenancyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_platform_audit(
        client,
        actor_user_id=auth_user_id,
        action="resource_grant.revoked",
        resource_type=str(grant.get("resource_type") or "resource"),
        resource_id=str(grant.get("resource_id") or body.grant_id),
        organization_id=body.organization_id,
        workspace_id=grant.get("workspace_id"),
        detail={"grant_id": body.grant_id},
    )
    return {"grant": grant}


@router.get("/governance/audit")
async def list_governance_audit(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    organization_id: str,
    limit: int = Query(default=100, ge=1, le=200),
):
    from app.services.platform_audit import list_platform_audit

    client = get_supabase_client()
    membership = (
        client.table("organization_members")
        .select("role")
        .eq("organization_id", organization_id)
        .eq("user_id", auth_user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if (membership.data or [{}])[0].get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Organization admin required")
    return {
        "events": list_platform_audit(
            client,
            organization_id=organization_id,
            limit=limit,
        )
    }


def _require_ops_admin(client, auth_user_id: str):
    membership = (
        client.table("organization_members")
        .select("organization_id,role")
        .eq("user_id", auth_user_id)
        .eq("status", "active")
        .in_("role", ["owner", "admin"])
        .limit(1)
        .execute()
    )
    if not membership.data:
        raise HTTPException(status_code=403, detail="Ops access denied")
    return membership.data[0]


@router.get("/ops/dead-letters")
async def list_ops_dead_letters(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    status: str = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=100),
):
    from app.services.job_dlq import list_dead_letters
    from app.services.platform_audit import record_admin_access

    client = get_supabase_client()
    # Ops endpoints stay service-backed; only org owners of any Enterprise org
    # may inspect the queue until a dedicated staff role exists.
    membership = _require_ops_admin(client, auth_user_id)
    record_admin_access(
        client,
        actor_user_id=auth_user_id,
        action="job_dlq.list",
        organization_id=membership.get("organization_id"),
        detail={"status": status},
    )
    return {"dead_letters": list_dead_letters(client, status=status, limit=limit)}


@router.get("/ops/workflow-health")
@limiter.limit("30/minute")
async def ops_workflow_health(
    request: Request,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    user_id: Optional[str] = Query(
        default=None,
        description="Optional user scope; defaults to caller. Cross-user requires ops admin.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Internal workflow health summary (Phase 7). Never public/unauthenticated."""
    from app.services.platform_audit import record_admin_access
    from app.services.workflow.observability import (
        build_workflow_health_summary,
        find_stuck_workflows,
        summarize_session_observability,
    )

    _ = request
    client = get_supabase_client()
    membership = _require_ops_admin(client, auth_user_id)
    scope_user = str(user_id or auth_user_id).strip()
    if scope_user != auth_user_id:
        # Cross-user inspection is admin-only (already checked) and audited.
        pass
    record_admin_access(
        client,
        actor_user_id=auth_user_id,
        action="workflow_health.summary",
        organization_id=membership.get("organization_id"),
        detail={"scope_user_id": scope_user, "limit": limit},
    )
    sessions_resp = (
        client.table("data_setup_sessions")
        .select(
            "id,user_id,status,source_type,created_at,updated_at,processing_progress"
        )
        .eq("user_id", scope_user)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    sessions = list(sessions_resp.data or [])
    session_ids = [str(s["id"]) for s in sessions if s.get("id")]
    steps: list = []
    if session_ids:
        # Bounded read — avoid N+1 by one IN query when supported; fallback batch.
        steps_resp = (
            client.table("workflow_steps")
            .select(
                "id,data_setup_session_id,step_type,status,version,attempt,"
                "created_at,updated_at,output,retryable"
            )
            .in_("data_setup_session_id", session_ids[:100])
            .limit(min(2000, limit * 12))
            .execute()
        )
        steps = list(steps_resp.data or [])
    summary = build_workflow_health_summary(sessions, steps)
    summary["scope_user_id"] = scope_user
    summary["stuck"] = find_stuck_workflows(sessions, steps)
    if sessions:
        latest = sessions[0]
        latest_steps = [
            s for s in steps
            if str(s.get("data_setup_session_id")) == str(latest.get("id"))
        ]
        summary["latest_session"] = summarize_session_observability(latest, latest_steps)
    return summary


@router.post("/ops/dead-letters")
@limiter.limit("20/minute")
async def update_ops_dead_letter(
    request: Request,
    body: JobDeadLetterUpdateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.job_dlq import JobDlqError, mark_dead_letter
    from app.services.platform_audit import record_admin_access

    _ = request
    client = get_supabase_client()
    membership = (
        client.table("organization_members")
        .select("organization_id,role")
        .eq("user_id", auth_user_id)
        .eq("status", "active")
        .in_("role", ["owner", "admin"])
        .limit(1)
        .execute()
    )
    if not membership.data:
        raise HTTPException(status_code=403, detail="Ops access denied")
    try:
        row = mark_dead_letter(
            client,
            dead_letter_id=body.dead_letter_id,
            status=body.status,
        )
    except JobDlqError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_admin_access(
        client,
        actor_user_id=auth_user_id,
        action="job_dlq.update",
        organization_id=membership.data[0].get("organization_id"),
        resource_type="job_dead_letter",
        resource_id=body.dead_letter_id,
        detail={"status": body.status},
    )
    return {"dead_letter": row}


@router.get("/visualizations/reports")
async def list_visualization_reports(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    source_message_id: Optional[str] = None,
):
    from app.services.visualizations import list_reports

    return {
        "reports": list_reports(
            auth_user_id,
            source_message_id=source_message_id,
        )
    }


@router.post("/visualizations/manual-source/scan")
@limiter.limit("20/minute")
async def scan_manual_visualization_source(
    request: Request,
    body: DataSetupScanRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Inspect an owned file for the manual Visualization builder without creating a setup session."""
    import asyncio

    from app.services.data_setup import build_scan_result, load_setup_handle

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if body.source_type not in {"file", "api", "sql", "cloud"}:
        raise HTTPException(status_code=400, detail="Unsupported source type")
    if body.source_type == "file" and not str(body.file_name or "").strip():
        raise HTTPException(status_code=400, detail="Select a file")
    if body.source_type != "file" and not body.connection_id:
        raise HTTPException(status_code=400, detail="Select a connection")
    if body.source_type == "sql" and not body.table_name:
        raise HTTPException(status_code=400, detail="Select a database table")
    file_name = str(body.file_name or "").strip()
    try:
        source_ref = {"file_name": file_name} if body.source_type == "file" else {
            "connection_id": body.connection_id,
            **({"table_name": body.table_name} if body.source_type == "sql" else {}),
        }
        if body.source_type == "cloud":
            from app.services.cloud_dataset import load_cloud_handle
            cloud = get_supabase_client().table("cloud_dataset_connections").select("*").eq("id", body.connection_id).eq("user_id", user_id).limit(1).execute()
            if not cloud.data:
                raise HTTPException(status_code=404, detail="Cloud dataset not found")
            handle, _ = await asyncio.to_thread(load_cloud_handle, cloud.data[0])
        else:
            handle = await asyncio.to_thread(
                load_setup_handle, user_id, body.source_type, source_ref, sample_only=False,
            )
        rows = json.loads(
            handle.to_pandas(limit=200).to_json(orient="records", date_format="iso")
        )
        scan = await asyncio.to_thread(
            build_scan_result,
            rows,
            source_type="file",
            source_label=file_name,
            row_count=handle.row_count(),
            row_count_exact=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not scan source file: {exc}") from exc
    return {"scan": scan}


@router.post("/visualizations/reports")
async def create_visualization_report(
    body: VisualizationReportCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, create_report

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        report = create_report(
            user_id,
            title=body.title,
            description=body.description or "",
            executive_summary=body.executive_summary or "",
            dataset_key=body.dataset_key,
            conversation_id=body.conversation_id,
            source_message_id=body.source_message_id,
            created_via=body.created_via,
            status=body.status,
            chart=body.chart.model_dump() if body.chart else None,
            dashboard_spec=body.dashboard_spec,
            source_config=body.source_config,
            pin=body.pin,
        )
        from app.services.customer_experience import record_dashboard_lineage_fail_safe
        created = bool(report.pop("_created", True))
        if created:
            record_dashboard_lineage_fail_safe(user_id, report)
        return {"report": report, "created": created}
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/visualizations/reports")
async def update_visualization_report(
    body: VisualizationReportUpdateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, update_report

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        updates = body.model_dump(
            exclude={"user_id", "report_id"},
            exclude_none=True,
        )
        return {
            "report": update_report(user_id, body.report_id, updates)
        }
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/visualizations/reports")
async def delete_visualization_report(
    body: VisualizationDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, delete_report

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if not body.report_id:
        raise HTTPException(status_code=400, detail="report_id is required")
    try:
        delete_report(user_id, body.report_id)
        return {"ok": True}
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/visualizations/reports/duplicate")
async def duplicate_visualization_report(
    body: VisualizationReportDuplicateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, duplicate_report

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return {
            "report": duplicate_report(
                user_id,
                body.report_id,
                title=body.title,
            )
        }
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/visualizations/charts")
async def create_visualization_chart(
    body: VisualizationChartCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, add_chart

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        chart = add_chart(
            user_id,
            body.report_id,
            body.chart.model_dump(),
            source_message_id=body.source_message_id,
        )
        return {"chart": chart}
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/visualizations/charts")
async def delete_visualization_chart(
    body: VisualizationDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, delete_chart

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if not body.chart_id:
        raise HTTPException(status_code=400, detail="chart_id is required")
    try:
        delete_chart(user_id, body.chart_id)
        return {"ok": True}
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/visualizations/dashboard/generate")
@limiter.limit("20/minute")
async def generate_visualization_dashboard(
    request: Request,
    body: VisualizationDashboardGenerateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, generate_dashboard

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        dashboard = generate_dashboard(
                user_id,
                body.report_id,
                force=body.force,
                filters=body.filters,
                dashboard_spec=body.dashboard_spec,
                persist=body.persist,
            )
        if body.persist:
            from app.services.customer_experience import (
                advance_onboarding_fail_safe,
            )
            advance_onboarding_fail_safe(
                user_id,
                "first_dashboard",
                first_dashboard_id=body.report_id,
            )
        return {"dashboard": dashboard}
    except VisualizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/visualizations/decision/reprove")
@limiter.limit("10/minute")
async def reprove_visualization_decision(
    request: Request,
    body: VisualizationDecisionReproveRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, reprove_decision_packet

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return reprove_decision_packet(
            user_id,
            body.report_id,
            filters=body.filters,
        )
    except VisualizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/visualizations/dashboard/plan")
@limiter.limit("10/minute")
async def plan_visualization_dashboard(
    request: Request,
    body: VisualizationDashboardPlanRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, plan_dashboard

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    await check_user_message_quota(user_id)
    try:
        return {
            "dashboard": await plan_dashboard(
                user_id,
                body.report_id,
                instruction=body.instruction,
                current_spec=body.current_spec,
            )
        }
    except VisualizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/visualizations/dashboard/revisions")
async def list_visualization_dashboard_revisions(
    report_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import list_dashboard_revisions

    return {
        "revisions": list_dashboard_revisions(auth_user_id, report_id)
    }


@router.post("/visualizations/dashboard/revisions/restore")
async def restore_visualization_dashboard_revision(
    body: VisualizationRevisionRestoreRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import (
        VisualizationError,
        restore_dashboard_revision,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return {
            "dashboard": restore_dashboard_revision(
                user_id,
                body.report_id,
                body.revision_id,
            )
        }
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/visualizations/shares")
async def list_visualization_shares(
    report_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import list_report_shares

    return {"shares": list_report_shares(auth_user_id, report_id)}


@router.post("/visualizations/shares")
@limiter.limit("20/minute")
async def create_visualization_share(
    request: Request,
    body: VisualizationShareCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, create_report_share

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return {
            "share": create_report_share(
                user_id,
                body.report_id,
                expires_in_days=body.expires_in_days,
                allow_detail_rows=body.allow_detail_rows,
                max_views=body.max_views,
            )
        }
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/visualizations/shares")
async def revoke_visualization_share(
    body: VisualizationShareRevokeRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import VisualizationError, revoke_report_share

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        revoke_report_share(user_id, body.report_id, body.share_id)
        return {"ok": True}
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/visualizations/shared/{token}")
@limiter.limit("30/minute")
async def get_shared_visualization(request: Request, token: str):
    from app.services.visualizations import VisualizationError, get_shared_dashboard

    try:
        return get_shared_dashboard(token)
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/visualizations/shared/{token}")
@limiter.limit("30/minute")
async def filter_shared_visualization(
    request: Request,
    token: str,
    body: SharedVisualizationFilterRequest,
):
    from app.services.visualizations import VisualizationError, get_shared_dashboard

    try:
        return get_shared_dashboard(
            token,
            filters=body.filters,
            count_view=False,
        )
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/automation/delivery/open/{token}")
@limiter.limit("60/minute")
async def mark_scheduled_delivery_open(request: Request, token: str):
    import base64
    import uuid

    try:
        normalized = str(uuid.UUID(token))
    except ValueError:
        normalized = ""
    if normalized:
        client = get_supabase_client()
        try:
            response = (
                client.table("automation_delivery_events")
                .select("id,opened_at")
                .eq("delivery_token", normalized)
                .eq("event_type", "delivered")
                .limit(1)
                .execute()
            )
            if response.data and not response.data[0].get("opened_at"):
                client.table("automation_delivery_events").update({
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", response.data[0]["id"]).execute()
        except Exception:
            pass
    pixel = base64.b64decode(
        "R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
    )
    return Response(
        content=pixel,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/visualizations/templates")
async def list_visualization_templates(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import list_dashboard_templates

    return {"templates": list_dashboard_templates(auth_user_id)}


@router.post("/visualizations/templates")
async def create_visualization_template(
    body: VisualizationTemplateCreateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import (
        VisualizationError,
        create_dashboard_template,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return {
            "template": create_dashboard_template(
                user_id,
                body.report_id,
                name=body.name,
            )
        }
    except (VisualizationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/visualizations/templates/preview")
async def preview_visualization_template(
    body: VisualizationTemplatePreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import (
        VisualizationError,
        preview_dashboard_template,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return {
            "dashboard": preview_dashboard_template(
                user_id,
                body.report_id,
                body.template_id,
                persist=body.persist,
            )
        }
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/visualizations/templates")
async def delete_visualization_template(
    body: VisualizationTemplateDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.visualizations import (
        VisualizationError,
        delete_dashboard_template,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        delete_dashboard_template(user_id, body.template_id)
        return {"ok": True}
    except VisualizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/files/upload")
@limiter.limit("30/minute")
async def upload_business_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    import os
    import re
    import tempfile
    import time

    original = file.filename or "upload"
    safe = re.sub(r"[^\w.\-\u0E00-\u0E7F]", "_", original, flags=re.UNICODE)
    safe = safe.strip("._-") or "file"
    storage_name = f"{int(time.time() * 1000)}_{safe}"
    storage_path = f"{auth_user_id}/{storage_name}"
    temp_path = None
    size = 0
    try:
        suffix = os.path.splitext(safe)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            temp_path = tmp.name
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                validate_upload_bytes(original, size)
                tmp.write(chunk)
        enforce_customer_storage_quota(auth_user_id, size, storage_path)
        with open(temp_path, "rb") as upload:
            get_supabase_client().storage.from_("business-data").upload(
                path=storage_path,
                file=upload,
                file_options={
                    "content-type": file.content_type or "application/octet-stream",
                    "upsert": "false",
                },
            )
        from app.services.etl_scheduler import run_on_upload_schedules

        background_tasks.add_task(
            run_on_upload_schedules,
            auth_user_id,
            storage_name,
        )
        return {"ok": True, "file_name": storage_name, "size_bytes": size}
    except (FileValidationError, StorageQuotaExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.post("/files/avatar")
@limiter.limit("20/minute")
async def upload_avatar(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    import time

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Avatar exceeds 5 MB")
    try:
        enforce_customer_storage_quota(auth_user_id, len(content))
    except StorageQuotaExceeded as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    original = file.filename or "avatar.jpg"
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else "jpg"
    ext = ext if ext in {"jpg", "jpeg", "png", "webp"} else "jpg"
    storage_path = f"{auth_user_id}/{int(time.time() * 1000)}.{ext}"
    bucket = get_supabase_client().storage.from_("avatars")
    bucket.upload(
        path=storage_path,
        file=content,
        file_options={"content-type": file.content_type or "image/jpeg", "upsert": "false"},
    )
    public = bucket.get_public_url(storage_path)
    public_url = public if isinstance(public, str) else public.get("publicUrl") or public.get("public_url")
    return {"ok": True, "path": storage_path, "public_url": public_url}


def _warm_ingest_task(user_id: str, file_name: str) -> None:
    try:
        load_handle_from_storage(user_id, file_name)
    except Exception as exc:
        logger.warning(
            "background_ingest_warm_failed",
            extra={"user_id": user_id, "file_name": file_name, "error_code": "source_operation_failed", "error": str(exc)},
        )


@router.post("/files/warm-ingest-cache")
@limiter.limit("30/minute")
async def warm_ingest_cache(
    request: Request,
    body: WarmIngestCacheRequest,
    background_tasks: BackgroundTasks,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if body.size_bytes is not None:
        try:
            validate_upload_bytes(body.file_name, body.size_bytes)
        except FileValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_warm_ingest_task, user_id, body.file_name)
    return {"ok": True, "queued": True, "file_name": body.file_name}


@router.post("/files/dataset-preview")
@limiter.limit("30/minute")
async def preview_dataset_identity(
    request: Request,
    body: JsonMappingPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Preview an owner-scoped stable dataset identity without exposing storage paths."""
    import asyncio
    import json

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        handle = await asyncio.to_thread(
            load_handle_from_storage,
            user_id,
            body.file_name,
        )
    except DatasetLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if handle is None:
        raise HTTPException(status_code=400, detail="Unsupported dataset")
    limit = max(1, min(int(body.max_rows or 10), 50))
    frame = handle.to_pandas(limit=limit)
    return {
        "dataset_key": body.file_name,
        "rows": json.loads(frame.to_json(orient="records", date_format="iso")),
    }


@router.get("/cloud-datasets")
async def list_cloud_datasets(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    response = (
        get_supabase_client().table("cloud_dataset_connections").select("*")
        .eq("user_id", auth_user_id).order("created_at", desc=True).execute()
    )
    return {"connections": response.data or []}


@router.post("/cloud-datasets/preview")
@limiter.limit("20/minute")
async def preview_cloud_dataset(
    request: Request,
    body: CloudDatasetRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Fetch a provider file transiently and return a bounded mapping preview."""
    import asyncio

    from app.services.cloud_dataset import load_cloud_handle, normalize_download_url

    require_matching_user_id(body.user_id, auth_user_id)
    if body.provider not in {"google", "microsoft"}:
        raise HTTPException(status_code=400, detail="Invalid cloud provider")
    try:
        normalize_download_url(body.provider, body.source_url, body.sheet_name)
        handle, metadata = await asyncio.to_thread(load_cloud_handle, body.model_dump())
        preview = handle.to_pandas(limit=50)
        rows = json.loads(preview.to_json(orient="records", date_format="iso"))
        return {
            "rows": rows,
            "columns": [str(column) for column in preview.columns],
            "row_count": handle.row_count(),
            "metadata": metadata,
        }
    except (ValueError, DatasetLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cloud-datasets")
async def save_cloud_dataset(
    body: CloudDatasetRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.cloud_dataset import normalize_download_url

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if body.provider not in {"google", "microsoft"}:
        raise HTTPException(status_code=400, detail="Invalid cloud provider")
    try:
        normalize_download_url(body.provider, body.source_url, body.sheet_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = body.model_dump(exclude={"user_id"})
    payload["user_id"] = user_id
    response = get_supabase_client().table("cloud_dataset_connections").insert(payload).execute()
    return {"connection": (response.data or [payload])[0]}


@router.delete("/cloud-datasets")
async def delete_cloud_dataset(
    body: CloudDatasetActionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    get_supabase_client().table("cloud_dataset_connections").delete().eq(
        "id", body.connection_id
    ).eq("user_id", user_id).execute()
    return {"ok": True}


@router.post("/cloud-datasets/refresh")
@limiter.limit("10/minute")
async def refresh_cloud_dataset(
    request: Request,
    body: CloudDatasetActionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Refresh a cloud link, apply its approved recipe, and publish versioned Parquet."""
    import asyncio
    import os
    import re
    import tempfile
    from datetime import datetime, timezone

    from app.services.cloud_dataset import load_cloud_handle
    from app.services.dataset_engine import DatasetHandle, TABLE_NAME
    from app.services.etl_pipeline import normalize_recipe

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    raise HTTPException(
        status_code=409,
        detail=(
            "Cloud refresh requires Adaptive Data Setup. Open this source in "
            "Chat, complete the questions, and approve the new DatasetVersion."
        ),
    )
    client = get_supabase_client()
    response = (
        client.table("cloud_dataset_connections").select("*")
        .eq("id", body.connection_id).eq("user_id", user_id).limit(1).execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Cloud dataset connection not found")
    connection = response.data[0]
    client.table("cloud_dataset_connections").update({
        "last_status": "syncing", "last_error": None,
    }).eq("id", body.connection_id).eq("user_id", user_id).execute()
    temp_path = None
    run_id = None
    try:
        handle, metadata = await asyncio.to_thread(load_cloud_handle, connection)
        unchanged = (
            not body.force
            and connection.get("content_hash")
            and connection.get("content_hash") == metadata["content_hash"]
        )
        now = datetime.now(timezone.utc).isoformat()
        if unchanged:
            client.table("cloud_dataset_connections").update({
                **metadata, "last_status": "unchanged", "last_synced_at": now,
            }).eq("id", body.connection_id).eq("user_id", user_id).execute()
            return {"ok": True, "changed": False, "status": "unchanged"}

        recipe = normalize_recipe({})
        recipe_id = connection.get("recipe_id")
        if recipe_id:
            recipe_response = (
                client.table("etl_recipes").select("*").eq("id", recipe_id)
                .eq("user_id", user_id).limit(1).execute()
            )
            if recipe_response.data:
                recipe = normalize_recipe(recipe_response.data[0].get("recipe"))
        _notes, handle = await asyncio.to_thread(
            handle.prepare_for_analysis,
            recipe.get("column_mapping") or {},
            recipe.get("cleaning_profile") or "standard",
            recipe,
        )

        dataset_key = f"cloud:{connection['provider']}:{connection['id']}"
        run_response = client.table("etl_pipeline_runs").insert({
            "user_id": user_id, "recipe_id": recipe_id,
            "dataset_key": dataset_key, "status": "running",
            "recipe_snapshot": recipe,
        }).execute()
        run_id = (run_response.data or [{}])[0].get("id")
        export_handle = DatasetHandle.for_sql_execution(handle)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            temp_path = tmp.name
        escaped = temp_path.replace("'", "''")
        export_handle._con.execute(
            f"COPY (SELECT * FROM {TABLE_NAME}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        stem = re.sub(
            r"[^A-Za-z0-9_\-\u0E00-\u0E7F]",
            "_",
            str(connection.get("display_name") or "cloud_dataset"),
        )
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Keep published results at the owner's bucket root so existing file/chat
        # selectors can analyze them without a second cloud-specific ingest path.
        output_name = f"cloud_etl_{stem}_v{version}.parquet"
        with open(temp_path, "rb") as upload_file:
            enforce_customer_storage_quota(user_id, os.path.getsize(temp_path), f"{user_id}/{output_name}")
            client.storage.from_("business-data").upload(
                path=f"{user_id}/{output_name}",
                file=upload_file,
                file_options={"content-type": "application/octet-stream", "upsert": "false"},
            )
        report = dict(handle._cleaning_report or {})
        run_update = {
            "status": "completed", "output_rows": handle.row_count(),
            "output_version": output_name, "report": report, "completed_at": now,
        }
        if run_id:
            client.table("etl_pipeline_runs").update(run_update).eq(
                "id", run_id
            ).eq("user_id", user_id).execute()
        client.table("cloud_dataset_connections").update({
            **metadata,
            "last_status": "completed",
            "last_synced_at": now,
            "latest_output_file": output_name,
            "last_error": None,
        }).eq("id", body.connection_id).eq("user_id", user_id).execute()
        return {
            "ok": True, "changed": True, "status": "completed",
            "output_file": output_name, "rows": handle.row_count(), "run_id": run_id,
        }
    except Exception as exc:
        now = datetime.now(timezone.utc).isoformat()
        client.table("cloud_dataset_connections").update({
            "last_status": "failed", "last_error": str(exc)[:1000],
            "last_synced_at": now,
        }).eq("id", body.connection_id).eq("user_id", user_id).execute()
        if run_id:
            client.table("etl_pipeline_runs").update({
                "status": "failed", "error_message": str(exc)[:1000],
                "completed_at": now,
            }).eq("id", run_id).eq("user_id", user_id).execute()
        raise HTTPException(status_code=400, detail=f"Cloud refresh failed: {exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.post("/files/json-mapping-preview")
@limiter.limit("20/minute")
async def json_mapping_preview(
    request: Request,
    body: JsonMappingPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Discover record-array paths and return only a bounded mapping sample."""
    import asyncio
    import os

    from app.services.json_paths import discover_record_paths, resolve_record_path
    from app.services.storage_download import download_business_data_to_path

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if not body.file_name.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON file required")

    def read_preview() -> Dict[str, Any]:
        path = download_business_data_to_path(user_id, body.file_name, suffix=".json")
        try:
            with open(path, encoding="utf-8") as source:
                payload = json.load(source)
            paths = discover_record_paths(payload)
            selected = body.json_path or (paths[0] if paths else None)
            rows = resolve_record_path(payload, selected) if selected else []
            if not rows and isinstance(payload, list):
                rows = [item for item in payload if isinstance(item, dict)]
            if not rows and isinstance(payload, dict):
                rows = [payload]
            return {
                "rows": rows[:max(1, min(body.max_rows, 50))],
                "json_paths": paths,
                "selected_json_path": selected,
            }
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    try:
        return await asyncio.to_thread(read_preview)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse JSON: {exc}") from exc


@router.post("/etl/preview")
@limiter.limit("20/minute")
async def preview_etl(
    request: Request,
    body: EtlPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Preview deterministic cleaning on a bounded sample before mapping/apply."""
    import asyncio

    from app.services.data_cleaning import clean_dataframe
    from app.services.etl_pipeline import (
        build_cleaning_preview,
        normalize_recipe,
        validate_data_contract,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        handle = await asyncio.to_thread(
            load_handle_from_storage, user_id, body.file_name, None
        )
        if handle is None:
            raise HTTPException(status_code=400, detail="Unsupported tabular file")
        total_rows = handle.row_count()
        sampled = handle.is_large or total_rows > 10_000
        before = handle.to_pandas(limit=10_000)
        _notes, after = await asyncio.to_thread(
            clean_dataframe,
            before,
            body.column_mapping,
            body.cleaning_profile or "standard",
            normalize_recipe(body.recipe),
        )
        report = dict(after.attrs.get("cleaning_report") or {})
        normalized_recipe = normalize_recipe(body.recipe)
        payload = build_cleaning_preview(
            before,
            after,
            report,
            body.column_mapping,
            sampled=sampled,
            total_rows=total_rows,
        )
        payload["contract_readiness"] = validate_data_contract(
            normalized_recipe.get("data_contract"),
            body.column_mapping or normalized_recipe.get("column_mapping"),
            list(map(str, before.columns)),
        )
        try:
            get_supabase_client().table("etl_pipeline_runs").insert({
                "user_id": user_id,
                "dataset_key": body.file_name,
                "status": "previewed",
                "recipe_snapshot": normalized_recipe,
                "input_rows": total_rows,
                "output_rows": payload["rows_after"],
                "report": payload,
            }).execute()
        except Exception as exc:
            if "etl_pipeline_runs" not in str(exc):
                logger.warning(
                    "etl_preview_audit_unavailable",
                    extra={"error_code": "persistence_failed", "error": str(exc)},
                )
        return payload
    except HTTPException:
        raise
    except DatasetLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _owned_data_setup(client, session_id: str, user_id: str) -> Dict[str, Any]:
    response = client.table("data_setup_sessions").select("*").eq(
        "id", session_id
    ).eq("user_id", user_id).limit(1).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Data setup session not found")
    return response.data[0]


def _structured_setup_conflict(
    session: Dict[str, Any],
    *,
    conversation_id: Optional[str],
) -> Dict[str, Any]:
    status = str(session.get("status") or "")
    ready = status == "ready"
    resumable = status in {
        "scanning", "awaiting_answers", "previewing", "preview_ready",
        "approved", "processing",
    }
    return {
        "code": "READY_DATASET_EXISTS" if ready else "ACTIVE_SETUP_EXISTS",
        "existing_session_id": session.get("id"),
        "existing_conversation_id": session.get("conversation_id"),
        "status": status,
        "resumable": resumable,
        "ready_for_analysis": ready,
        "requested_conversation_id": conversation_id,
    }


def _data_setup_scan_response(
    session: Dict[str, Any],
    *,
    resumed: bool,
    user_id: str,
) -> Dict[str, Any]:
    """Return session plus optional WorkflowPlan for conversational entry."""
    payload: Dict[str, Any] = {"session": session, "resumed": resumed}
    if not settings.ENABLE_CONVERSATIONAL_DATA_SETUP:
        return payload
    try:
        from app.services.orchestrator.ui_payload import (
            build_source_summary,
            build_workflow_progress,
        )
        from app.services.workflow.engine import WorkflowEngine

        plan = WorkflowEngine().get_workflow_plan(
            str(session["id"]),
            session=session,
            user_id=user_id,
        )
        plan_dict = plan if isinstance(plan, dict) else dict(plan or {})
        payload["workflow"] = build_workflow_progress(plan_dict, session=session)
        payload["source"] = build_source_summary(session)
    except Exception:
        # Scan must succeed even if workflow bootstrap is unavailable.
        pass
    return payload


def _claim_data_setup_session(client, session_id: str, user_id: str) -> list[Dict[str, Any]]:
    try:
        response = client.rpc(
            "claim_data_setup_session", {"p_session_id": session_id}
        ).execute()
        return response.data or []
    except Exception as exc:
        if "service_role required" not in str(exc):
            raise
        # Compatibility for projects whose legacy RPC checks JWT claims that
        # opaque Supabase secret keys do not populate. The status predicate
        # keeps this fallback atomic until the hardened migration is applied.
        response = (
            client.table("data_setup_sessions")
            .update({
                "status": "processing",
                "current_step": "processing",
                "processing_progress": {"percent": 5, "stage": "claimed"},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", session_id)
            .eq("user_id", user_id)
            .eq("status", "approved")
            .execute()
        )
        return response.data or []


@router.post("/data-setup/scan")
@limiter.limit("20/minute")
async def scan_data_setup_source(
    request: Request,
    body: DataSetupScanRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Run a bounded source scan and persist metadata without storing raw sample rows."""
    import asyncio
    import uuid

    from app.services.data_setup import build_scan_result, load_setup_handle
    from app.services.storage_download import get_storage_object_metadata

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    conversation_id = _trusted_conversation_id(user_id, body.conversation_id)
    source_ref: Dict[str, Any]
    source_label: str
    source_version: Dict[str, Any] = {}
    if body.source_type == "file":
        file_name = str(body.file_name or "").strip()
        if not file_name:
            raise HTTPException(status_code=400, detail="Select a file")
        try:
            source_version = get_storage_object_metadata(
                settings.AGENT_SESSION_STORAGE_BUCKET, f"{user_id}/{file_name}"
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Source file not found") from exc
        source_ref = {"file_name": file_name}
        source_label = file_name
    elif body.source_type == "api":
        if not body.connection_id:
            raise HTTPException(status_code=400, detail="Select an API connection")
        source_ref = {"connection_id": body.connection_id}
        source_label = "API connection"
    elif body.source_type == "sql":
        if not body.connection_id or not body.table_name:
            raise HTTPException(status_code=400, detail="Select a database table")
        source_ref = {"connection_id": body.connection_id, "table_name": body.table_name}
        source_label = body.table_name
    else:
        if not body.connection_id:
            raise HTTPException(status_code=400, detail="Select a cloud dataset")
        cloud_response = (
            get_supabase_client().table("cloud_dataset_connections").select(
                "id, display_name, content_hash, etag, last_modified"
            )
            .eq("id", body.connection_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not cloud_response.data:
            raise HTTPException(status_code=404, detail="Cloud dataset not found")
        cloud_connection = cloud_response.data[0]
        source_ref = {"connection_id": body.connection_id}
        source_label = (
            str(cloud_connection.get("display_name") or "").strip()
            or "Cloud dataset"
        )
        source_version = {
            key: cloud_connection.get(key)
            for key in ("content_hash", "etag", "last_modified")
            if cloud_connection.get(key)
        }

    rows = body.sample_rows
    actual_rows = None
    exact = body.row_count_exact
    if not rows:
        try:
            handle = await asyncio.to_thread(
                load_setup_handle,
                user_id,
                body.source_type,
                source_ref,
                sample_only=body.source_type != "file",
            )
            rows = json.loads(
                handle.to_pandas(limit=200).to_json(orient="records", date_format="iso")
            )
            actual_rows = handle.row_count()
            if body.source_type == "file":
                exact = True
        except Exception as exc:
            err = str(exc).strip() or type(exc).__name__
            lower = err.lower()
            if any(
                token in lower
                for token in (
                    "not found",
                    "signed url",
                    "404",
                    "object not found",
                    "could not create signed url",
                )
            ):
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Source file not found in storage. "
                        "Re-upload it from File Manager, then try again."
                    ),
                ) from exc
            raise HTTPException(
                status_code=400,
                detail=f"Quick Scan failed: {err}",
            ) from exc
    try:
        scan = await asyncio.to_thread(
            build_scan_result,
            rows,
            source_type=body.source_type,
            source_label=source_label,
            row_count=body.row_count_estimate if body.row_count_estimate is not None else actual_rows,
            row_count_exact=exact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    import hashlib

    scan["source_fingerprint"] = hashlib.sha256(
        json.dumps(
            {
                "schema_fingerprint": scan["source_fingerprint"],
                "source_ref": source_ref,
                "source_version": source_version,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    client = get_supabase_client()
    existing = (
        client.table("data_setup_sessions").select("*")
        .eq("user_id", user_id)
        .eq("source_fingerprint", scan["source_fingerprint"])
        .in_("status", [
            "scanning", "awaiting_answers", "previewing", "preview_ready",
            "approved", "processing", "ready",
        ])
        .order("updated_at", desc=True).limit(1).execute()
    )
    if existing.data:
        found = existing.data[0]
        found_conversation = found.get("conversation_id")
        if found.get("status") == "ready" and not body.reuse_existing:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=409,
                content=_structured_setup_conflict(found, conversation_id=conversation_id),
            )
        if (
            found_conversation
            and conversation_id
            and found_conversation != conversation_id
            and not body.reuse_existing
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=409,
                content=_structured_setup_conflict(found, conversation_id=conversation_id),
            )
        resume_updates = {}
        if conversation_id and found_conversation != conversation_id:
            resume_updates["conversation_id"] = conversation_id
        elif conversation_id and not found_conversation:
            resume_updates["conversation_id"] = conversation_id
        if found.get("current_step") == "scan":
            resume_updates["current_step"] = "structure"
        if body.original_prompt.strip() and (
            body.original_prompt.strip() != str(found.get("original_prompt") or "")
        ):
            resume_updates["original_prompt"] = body.original_prompt.strip()
        if resume_updates:
            resume_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = client.table("data_setup_sessions").update(
                resume_updates
            ).eq("id", found["id"]).eq("user_id", user_id).execute()
            found = (updated.data or [found])[0]
        return _data_setup_scan_response(found, resumed=True, user_id=user_id)
    session_id = str(uuid.uuid4())
    payload = {
        "id": session_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "source_type": body.source_type,
        "source_ref": source_ref,
        "source_fingerprint": scan["source_fingerprint"],
        "status": "awaiting_answers",
        "current_step": "structure",
        "original_prompt": body.original_prompt.strip(),
        "scan_result": scan,
        "column_mapping": scan["suggested_mapping"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.table("data_setup_sessions").insert(payload).execute()
    saved = (response.data or [payload])[0]
    return _data_setup_scan_response(saved, resumed=False, user_id=user_id)


@router.get("/data-setup/resume")
@limiter.limit("60/minute")
async def resume_data_setup_session(
    request: Request,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    source_type: Literal["file", "api", "sql", "cloud"],
    file_name: Optional[str] = None,
    connection_id: Optional[str] = None,
    table_name: Optional[str] = None,
    conversation_id: Optional[str] = None,
):
    _ = request
    conversation_id = _trusted_conversation_id(auth_user_id, conversation_id)
    expected_ref = (
        {"file_name": file_name}
        if source_type == "file"
        else {
            "connection_id": connection_id,
            **({"table_name": table_name} if source_type == "sql" else {}),
        }
    )
    response = (
        get_supabase_client().table("data_setup_sessions").select("*")
        .eq("user_id", auth_user_id).eq("source_type", source_type)
        .in_("status", [
            "awaiting_answers", "previewing", "preview_ready", "approved",
            "processing", "ready", "failed",
        ])
        .order("updated_at", desc=True).limit(25).execute()
    )
    for session in response.data or []:
        if (session.get("source_ref") or {}) != expected_ref:
            continue
        if conversation_id and session.get("conversation_id") not in {None, conversation_id}:
            continue
        if not conversation_id and session.get("conversation_id") is not None:
            continue
        payload = {"session": session}
        try:
            from app.services.workflow.state import get_resume_state

            resume = get_resume_state(str(session.get("id") or ""))
            latest = resume.get("steps") or {}
            current = resume.get("next_step") or session.get("next_action")
            step_status = None
            if current and current in latest:
                step_status = latest[current].get("status")
            elif session.get("status") == "ready":
                current = "finalize"
                step_status = "completed"
            # Additive optional fields — existing clients ignore unknown keys.
            payload["workflow"] = {
                "current_step": current,
                "step_status": step_status,
                "last_failed_step": resume.get("last_failed_step")
                or session.get("last_failed_step"),
            }
        except Exception as exc:
            logger.warning(
                "data_setup_resume_workflow_enrich_failed",
                extra={"error": str(exc)[:240]},
            )
            payload["reconcile_error"] = "workflow_enrich_failed"
        if settings.ENABLE_CONVERSATIONAL_DATA_SETUP:
            try:
                from app.services.orchestrator.ui_payload import (
                    _session_active_decision,
                    build_source_summary,
                    build_workflow_progress,
                )
                from app.services.orchestrator.orchestrator import (
                    repair_missing_active_decision,
                )
                from app.services.workflow.engine import WorkflowEngine

                plan = WorkflowEngine().get_workflow_plan(
                    str(session.get("id") or ""),
                    session=session,
                    user_id=auth_user_id,
                )
                plan_dict = plan if isinstance(plan, dict) else dict(plan or {})
                next_action = plan_dict.get("next_action") or {}
                session, _ = repair_missing_active_decision(
                    get_supabase_client(),
                    session_id=str(session.get("id") or ""),
                    user_id=auth_user_id,
                    session=session,
                    step_type=str(next_action.get("step_type") or "") or None,
                )
                payload["session"] = session
                payload["workflow"] = build_workflow_progress(
                    plan_dict, session=session
                )
                payload["source"] = build_source_summary(session)
                progress = session.get("processing_progress") or {}
                active = _session_active_decision(session)
                payload["active_decision"] = active
                if active and str(active.get("status") or "") == "pending":
                    payload["awaiting_user"] = {
                        "decision_key": active.get("decision_key"),
                        "question": active.get("question"),
                        "options": list(active.get("options") or []),
                        "expected_input": active.get("expected_input"),
                        "free_text_allowed": active.get("free_text_allowed", True),
                        "step_type": active.get("step_type"),
                        "reason_code": active.get("reason_code"),
                        "context": active.get("context"),
                    }
                else:
                    payload["awaiting_user"] = None
                if isinstance(progress, Mapping):
                    resolved = progress.get("resolved_decision_key")
                    if resolved:
                        payload["resolved_decision_key"] = str(resolved)
                stamps = progress.get("worklog_stamps") if isinstance(progress, Mapping) else None
                if isinstance(stamps, list) and stamps:
                    payload["worklog_stamps"] = [dict(s) for s in stamps if isinstance(s, Mapping)][-8:]
                payload["session_status"] = session.get("status")
                payload["updated_at"] = session.get("updated_at")
            except Exception as exc:
                logger.warning(
                    "data_setup_resume_orchestrator_enrich_failed",
                    extra={
                        "session_id": str(session.get("id") or ""),
                        "error": str(exc)[:240],
                    },
                )
                payload["reconcile_error"] = "orchestrator_enrich_failed"
                payload["enrich_error"] = str(exc)[:200]
            if (
                str((payload.get("session") or session).get("status") or "")
                == "awaiting_answers"
                and not payload.get("active_decision")
            ):
                # A resolved answer can retire active_decision at the exact
                # point where a bounded controller turn ends. Resume remains
                # read-mostly: expose an explicit continuation instead of a
                # dead "reload" loop with no answerable question.
                payload["continuation_available"] = True
                payload["stop_reason"] = "missing_active_decision"
        return payload
    return {"session": None}


@router.get("/data-setup/{session_id}")
@limiter.limit("60/minute")
async def get_data_setup_session(
    request: Request,
    session_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    return {"session": _owned_data_setup(get_supabase_client(), session_id, auth_user_id)}


@router.patch("/data-setup/{session_id}")
@limiter.limit("60/minute")
async def save_data_setup_draft(
    request: Request,
    session_id: str,
    body: DataSetupDraftRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    _owned_data_setup(client, session_id, user_id)
    payload = {
        "current_step": body.current_step,
        "answers": body.answers,
        "column_mapping": body.column_mapping,
        "cleaning_profile": body.cleaning_profile,
        "cleaning_recipe": body.cleaning_recipe,
        "business_context": body.business_context,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    return {"session": (response.data or [payload])[0]}


@router.post("/data-setup/{session_id}/preview")
@limiter.limit("20/minute")
async def preview_data_setup_cleaning(
    request: Request,
    session_id: str,
    body: DataSetupPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    import asyncio

    from app.services.data_setup import load_setup_handle, preview_setup_rows

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    session = _owned_data_setup(client, session_id, user_id)
    client.table("data_setup_sessions").update({
        "status": "previewing", "current_step": "cleaning",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).eq("user_id", user_id).execute()
    rows = body.sample_rows
    if not rows:
        try:
            handle = await asyncio.to_thread(
                load_setup_handle,
                user_id,
                session["source_type"],
                session.get("source_ref") or {},
                sample_only=True,
            )
            rows = json.loads(
                handle.to_pandas(limit=200).to_json(orient="records", date_format="iso")
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Cleaning preview failed: {exc}") from exc
    try:
        preview = await asyncio.to_thread(
            preview_setup_rows,
            rows,
            mapping=body.column_mapping,
            cleaning_profile=body.cleaning_profile,
            recipe=body.cleaning_recipe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {
        "status": "preview_ready",
        "current_step": "cleaning",
        "answers": body.answers,
        "column_mapping": body.column_mapping,
        "cleaning_profile": body.cleaning_profile,
        "cleaning_recipe": body.cleaning_recipe,
        "business_context": body.business_context,
        "preview_result": preview,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    return {"preview": preview, "session": (response.data or [payload])[0]}


@router.post("/data-setup/{session_id}/approve")
@limiter.limit("10/minute")
async def approve_data_setup(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str,
    body: DataSetupApproveRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.data_setup import process_data_setup_session
    from app.services.etl_pipeline import normalize_recipe, validate_data_contract

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    session = _owned_data_setup(client, session_id, user_id)
    if session.get("status") not in {"preview_ready", "approved", "failed"}:
        raise HTTPException(status_code=409, detail="Complete Cleaning Preview before approval")
    domain = str(body.answers.get("domain") or "").strip()
    if not domain or (
        domain == "other" and not str(body.answers.get("domain_other") or "").strip()
    ):
        raise HTTPException(status_code=422, detail="Dataset meaning is required")
    grain = str(body.answers.get("grain") or "").strip()
    if not grain or (grain == "other" and not str(body.answers.get("grain_other") or "").strip()):
        raise HTTPException(status_code=422, detail="Row grain is required")
    mapping = {key: value for key, value in body.column_mapping.items() if str(value).strip()}
    if not mapping:
        raise HTTPException(status_code=422, detail="Confirm at least one column mapping")
    scan_columns = (session.get("scan_result") or {}).get("columns") or []
    unresolved_critical = [
        item.get("name") for item in scan_columns
        if item.get("critical") and not mapping.get(item.get("name"))
    ]
    if unresolved_critical:
        raise HTTPException(
            status_code=422,
            detail=f"Confirm critical mappings: {', '.join(unresolved_critical[:10])}",
        )
    required_questions = [
        item for item in (session.get("scan_result") or {}).get("business_questions", [])
        if item.get("required")
    ]
    missing_context = []
    for item in required_questions:
        question_id = item.get("id")
        value = str(body.business_context.get(question_id) or "").strip()
        other_value = str(body.business_context.get(f"{question_id}_other") or "").strip()
        if not value or (value == "other" and not other_value):
            missing_context.append(item.get("label"))
    if missing_context:
        raise HTTPException(
            status_code=422,
            detail=f"Complete required business context: {', '.join(missing_context[:10])}",
        )
    preview = session.get("preview_result") or {}
    resolutions = body.cleaning_recipe.get("setup_issue_resolutions") or {}
    required_issue_keys = []
    required_issue_keys.extend(
        f"missing:{item.get('column')}" for item in preview.get("missing_recommendations", [])
    )
    required_issue_keys.extend(
        f"outlier:{item.get('column')}" for item in preview.get("outlier_candidates", [])
    )
    required_issue_keys.extend(
        f"invalid_date:{item.get('column')}" for item in preview.get("invalid_date_issues", [])
    )
    if int((preview.get("cleaning_report") or {}).get("dropped_duplicates") or 0) > 0:
        required_issue_keys.append("duplicates")
    unresolved_issues = [key for key in required_issue_keys if not resolutions.get(key)]
    if unresolved_issues:
        raise HTTPException(
            status_code=422,
            detail=f"Resolve detected cleaning issues: {', '.join(unresolved_issues[:10])}",
        )
    recipe = normalize_recipe({
        **body.cleaning_recipe,
        "cleaning_profile": body.cleaning_profile,
        "column_mapping": mapping,
    })
    readiness = validate_data_contract(
        recipe.get("data_contract"), mapping,
        [item.get("name") for item in scan_columns if item.get("name")],
    )
    if readiness["status"] != "ready":
        detail = readiness.get("errors") or readiness.get("missing") or readiness.get("warnings")
        raise HTTPException(
            status_code=422,
            detail={"message": "Data Contract must be ready before processing", "issues": detail},
        )
    payload = {
        "status": "approved", "current_step": "processing",
        "answers": body.answers, "column_mapping": mapping,
        "cleaning_profile": body.cleaning_profile,
        "cleaning_recipe": recipe,
        "business_context": body.business_context,
        "error_message": None,
        "processing_progress": {"percent": 5, "stage": "queued"},
        "approved_by": user_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    from app.services.platform_audit import record_platform_audit
    from app.services.sli import measure_sli

    with measure_sli("quick_scan"):
        record_platform_audit(
            client,
            actor_user_id=user_id,
            action="data_setup.approved",
            resource_type="data_setup_session",
            resource_id=session_id,
            organization_id=session.get("organization_id"),
            workspace_id=session.get("workspace_id"),
            detail={
                "recipe_hash": (recipe or {}).get("recipe_hash"),
                "contract_ready": True,
            },
        )
    # Persist dataset-scoped mapping with generated column contracts. Raw samples
    # never enter this memory table.
    dataset_key = str((session.get("source_ref") or {}).get("file_name") or f"{session['source_type']}:{(session.get('source_ref') or {}).get('connection_id')}")
    column_contracts = (recipe.get("data_contract") or {}).get("column_contracts") or {}
    if mapping:
        client.table("dataset_mapping_memory").upsert([
            {
                "user_id": user_id, "dataset_key": dataset_key,
                "original_column": column, "mapped_semantic": role,
                "column_contract": column_contracts.get(column) or {},
                "mapping_source": "suggested", "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for column, role in mapping.items()
        ], on_conflict="user_id,dataset_key,original_column").execute()
    claimed = _claim_data_setup_session(client, session_id, user_id)
    if claimed:
        background_tasks.add_task(process_data_setup_session, session_id, user_id)
    return {"session": (response.data or [payload])[0], "contract_readiness": readiness}


@router.post("/data-setup/{session_id}/cancel")
@limiter.limit("20/minute")
async def cancel_data_setup(
    request: Request,
    session_id: str,
    body: DataSetupCancelRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    session = _owned_data_setup(client, session_id, user_id)
    if session.get("status") in {"approved", "processing", "ready"}:
        raise HTTPException(status_code=409, detail="Processing sessions cannot be cancelled here")
    payload = {
        "status": "cancelled",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.table("data_setup_sessions").update(payload).eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    return {"session": (response.data or [payload])[0]}


@router.get("/etl/recipes")
async def list_etl_recipes(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
    dataset_key: Optional[str] = None,
):
    query = (
        get_supabase_client().table("etl_recipes").select("*")
        .eq("user_id", auth_user_id)
    )
    if dataset_key:
        query = query.eq("dataset_key", dataset_key)
    response = query.order("updated_at", desc=True).execute()
    return {"recipes": response.data or []}


@router.post("/etl/recipes")
async def save_etl_recipe(
    body: EtlRecipeRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.etl_pipeline import (
        normalize_recipe,
        recipe_hash,
        validate_data_contract,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    normalized = normalize_recipe(body.recipe)
    normalized["contract_validation"] = validate_data_contract(
        normalized.get("data_contract"),
        normalized.get("column_mapping"),
        list(normalized.get("column_mapping") or {}),
    )
    existing = (
        client.table("etl_recipes").select("version")
        .eq("user_id", user_id).eq("dataset_key", body.dataset_key)
        .order("version", desc=True).limit(1).execute()
    )
    version = int(existing.data[0]["version"]) + 1 if existing.data else 1
    payload = {
        "user_id": user_id, "dataset_key": body.dataset_key,
        "name": body.name.strip()[:120] or "Cleaning recipe",
        "version": version, "recipe": normalized,
        "recipe_hash": recipe_hash(normalized), "is_active": True,
    }
    if body.recipe_id:
        response = (
            client.table("etl_recipes").update(payload)
            .eq("id", body.recipe_id).eq("user_id", user_id).execute()
        )
    else:
        response = client.table("etl_recipes").insert(payload).execute()
    return {"recipe": (response.data or [payload])[0]}


@router.delete("/etl/recipes")
async def delete_etl_recipe(
    body: EtlRecipeDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    get_supabase_client().table("etl_recipes").delete().eq(
        "id", body.recipe_id
    ).eq("user_id", user_id).execute()
    return {"ok": True}


@router.get("/etl/schedules")
async def list_etl_schedules(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    client = get_supabase_client()
    response = (
        client.table("etl_schedules")
        .select("*, etl_recipes(id,name,dataset_key,version)")
        .eq("user_id", auth_user_id)
        .order("created_at", desc=True)
        .execute()
    )
    runs = (
        client.table("etl_pipeline_runs")
        .select(
            "id,schedule_id,recipe_id,dataset_key,output_dataset_key,status,trigger_kind,"
            "output_version,error_message,started_at,completed_at,created_at"
        )
        .eq("user_id", auth_user_id)
        .not_.is_("schedule_id", "null")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    events_data = []
    conversations_data = []
    try:
        events = (
            client.table("automation_delivery_events")
            .select("id,schedule_id,run_id,event_type,severity,reason_codes,metrics,delivery_channel,created_at,opened_at")
            .eq("user_id", auth_user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        events_data = events.data or []
    except Exception:
        pass
    try:
        conversations = (
            client.table("conversations")
            .select("id,title,created_at")
            .eq("user_id", auth_user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        conversations_data = conversations.data or []
    except Exception:
        pass
    delivered = sum(1 for item in events_data if item.get("event_type") == "delivered")
    opened = sum(1 for item in events_data if item.get("opened_at"))
    return {
        "schedules": response.data or [],
        "runs": runs.data or [],
        "automation_events": events_data,
        "conversations": conversations_data,
        "delivery_metrics": {
            "delivered": delivered,
            "opened": opened,
            "open_rate": round(opened / delivered, 4) if delivered else None,
        },
        "schedule_limit": settings.ETL_MAX_SCHEDULES_PER_USER,
    }


@router.post("/etl/schedules/preview")
@limiter.limit("20/minute")
async def preview_etl_schedule_guardrails(
    request: Request,
    body: EtlSchedulePreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.automation_guardrails import (
        evaluate_delivery_candidate,
        normalize_automation_config,
    )

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    recipe_response = (
        client.table("etl_recipes")
        .select("id,recipe")
        .eq("id", body.recipe_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not recipe_response.data:
        raise HTTPException(status_code=404, detail="ETL recipe not found")
    config = normalize_automation_config(body.alert_config)
    delivery_channels = []
    if config.get("delivery_enabled"):
        delivery_channels.append("email")
    chat_target_valid = False
    if body.chat_delivery_enabled:
        delivery_channels.append("chat")
        if body.chat_target_conversation_id:
            target = (
                client.table("conversations")
                .select("id")
                .eq("id", body.chat_target_conversation_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            chat_target_valid = bool(target.data)
    config["preview_acknowledged"] = True
    decision = evaluate_delivery_candidate(
        config=config,
        data_contract=(recipe_response.data[0].get("recipe") or {}).get("data_contract"),
        fingerprint="preview",
        previous_fingerprint=None,
        current_rows=0,
        previous_rows=None,
        source_updated_at=datetime.now(timezone.utc).isoformat(),
        quality_alerts=[],
        delivery_channels=delivery_channels,
        chat_target_valid=chat_target_valid,
    )
    decision["reason_codes"] = [
        code for code in decision["reason_codes"]
        if code not in {"duplicate_fingerprint", "change_below_threshold"}
    ]
    decision["decision"] = "eligible" if not decision["reason_codes"] else "suppressed"
    if body.schedule_id:
        try:
            client.table("automation_delivery_events").insert({
                "user_id": user_id,
                "schedule_id": body.schedule_id,
                "event_type": "previewed",
                "severity": decision["severity"],
                "fingerprint": decision["decision_fingerprint"],
                "reason_codes": decision["reason_codes"],
                "metrics": {"delivery_sent": False},
            }).execute()
        except Exception:
            pass
    return {"config": config, "preview": decision}


@router.post("/etl/schedules")
@limiter.limit("20/minute")
async def save_etl_schedule(
    request: Request,
    body: EtlScheduleRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from datetime import datetime, timezone
    import uuid

    from app.services.etl_execution import build_output_dataset_key
    from app.services.etl_schedule import CronExpressionError, calculate_next_run
    from app.services.automation_guardrails import normalize_automation_config

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    if body.schedule_kind not in {"manual", "cron", "on_upload"}:
        raise HTTPException(status_code=400, detail="Invalid schedule kind")
    client = get_supabase_client()
    if not body.schedule_id:
        schedule_count = (
            client.table("etl_schedules")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        if int(schedule_count.count or 0) >= settings.ETL_MAX_SCHEDULES_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=f"Workspace schedule limit reached ({settings.ETL_MAX_SCHEDULES_PER_USER})",
            )
    recipe = (
        client.table("etl_recipes")
        .select("id,dataset_key")
        .eq("id", body.recipe_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not recipe.data:
        raise HTTPException(status_code=404, detail="ETL recipe not found")
    recipe_dataset_key = str(recipe.data[0].get("dataset_key") or "").strip()
    if body.chat_delivery_enabled:
        if body.schedule_kind != "cron" or body.chat_delivery_weekday is None:
            raise HTTPException(
                status_code=400,
                detail="Chat delivery requires one weekday from Monday to Sunday",
            )
        if not body.chat_target_conversation_id:
            raise HTTPException(status_code=400, detail="Select a target conversation")
        target = (
            client.table("conversations")
            .select("id")
            .eq("id", body.chat_target_conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not target.data:
            raise HTTPException(status_code=404, detail="Target conversation not found")
        duplicate_query = (
            client.table("etl_schedules")
            .select("id")
            .eq("user_id", user_id)
            .eq("chat_delivery_enabled", True)
            .eq("chat_source_dataset_key", recipe_dataset_key)
        )
        if body.schedule_id:
            duplicate_query = duplicate_query.neq("id", body.schedule_id)
        if duplicate_query.limit(1).execute().data:
            raise HTTPException(
                status_code=409,
                detail="This dataset already has a weekly chat destination",
            )
        cron_weekday = 0 if body.chat_delivery_weekday == 7 else body.chat_delivery_weekday
        cron_expression = (
            f"{body.chat_delivery_minute} {body.chat_delivery_hour} * * {cron_weekday}"
        )
    else:
        cron_expression = body.cron_expression
    try:
        next_run = calculate_next_run(
            body.schedule_kind,
            cron_expression,
            body.timezone,
            enabled=body.enabled,
        )
    except CronExpressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    automation_config = normalize_automation_config(body.alert_config)
    if body.enabled and not automation_config.get("preview_acknowledged"):
        raise HTTPException(
            status_code=409,
            detail="Automation guardrail preview is required before enabling a schedule",
        )
    payload = {
        "user_id": user_id, "recipe_id": body.recipe_id,
        "schedule_kind": body.schedule_kind,
        "cron_expression": (
            cron_expression.strip() if body.schedule_kind == "cron" and cron_expression else None
        ),
        "timezone": body.timezone,
        "output_name": (body.output_name or "").strip()[:120] or None,
        "incremental_column": body.incremental_column,
        "alert_config": automation_config,
        "enabled": body.enabled,
        "next_run_at": next_run.isoformat() if next_run else None,
        "last_status": "scheduled" if body.enabled else "paused",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "chat_delivery_enabled": body.chat_delivery_enabled,
        "chat_delivery_weekday": (
            body.chat_delivery_weekday if body.chat_delivery_enabled else None
        ),
        "chat_delivery_hour": body.chat_delivery_hour,
        "chat_delivery_minute": body.chat_delivery_minute,
        "chat_target_conversation_id": (
            body.chat_target_conversation_id if body.chat_delivery_enabled else None
        ),
        "chat_source_dataset_key": (
            recipe_dataset_key if body.chat_delivery_enabled else None
        ),
        "chat_delivery_prompt": (
            (body.chat_delivery_prompt or "").strip()[:1000] or None
            if body.chat_delivery_enabled else None
        ),
    }
    if body.schedule_id:
        response = client.table("etl_schedules").update(payload).eq(
            "id", body.schedule_id
        ).eq("user_id", user_id).execute()
    else:
        schedule_id = str(uuid.uuid4())
        payload["id"] = schedule_id
        payload["output_dataset_key"] = build_output_dataset_key(schedule_id)
        response = client.table("etl_schedules").insert(payload).execute()
    return {"schedule": (response.data or [payload])[0]}


@router.post("/etl/schedules/run")
@limiter.limit("10/minute")
async def run_etl_schedule_now(
    request: Request,
    body: EtlScheduleActionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    import asyncio

    from app.services.etl_execution import EtlExecutionError
    from app.services.etl_scheduler import run_schedule_now

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    client = get_supabase_client()
    owned = (
        client.table("etl_schedules")
        .select("id")
        .eq("id", body.schedule_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="ETL schedule not found")
    try:
        return await asyncio.to_thread(
            run_schedule_now,
            body.schedule_id,
            client=client,
        )
    except EtlExecutionError as exc:
        status_code = 409 if "already running" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/etl/schedules")
@limiter.limit("20/minute")
async def delete_etl_schedule(
    request: Request,
    body: EtlScheduleDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    get_supabase_client().table("etl_schedules").delete().eq(
        "id", body.schedule_id
    ).eq("user_id", user_id).execute()
    return {"ok": True}


@router.post("/etl/run")
@limiter.limit("10/minute")
async def run_etl_recipe(
    request: Request,
    body: EtlRunRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Run a saved recipe, publish a versioned Parquet dataset, and persist audit/alerts."""
    import asyncio

    from app.services.etl_execution import EtlExecutionError, execute_etl_recipe

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return await asyncio.to_thread(
            execute_etl_recipe,
            user_id,
            body.recipe_id,
            output_name=body.output_name,
        )
    except EtlExecutionError as exc:
        raise HTTPException(status_code=400, detail=f"ETL run failed: {exc}") from exc


@router.get("/capabilities")
@limiter.limit("120/minute")
async def get_client_capabilities(request: Request):
    """Safe feature flags for frontend UX (no secrets)."""
    _ = request
    return {
        "conversational_data_setup": bool(
            settings.ENABLE_CONVERSATIONAL_DATA_SETUP
        ),
    }


@router.get("/analysis/metrics")
@limiter.limit("60/minute")
async def list_semantic_metrics(
    request: Request,
    dataset_key: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    return {
        "dataset_key": dataset_key,
        "definitions": fetch_custom_metrics(auth_user_id, dataset_key),
    }


@router.post("/analysis/metrics")
@limiter.limit("30/minute")
async def save_semantic_metric(
    request: Request,
    body: SemanticMetricRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        saved = upsert_custom_metric(user_id, body.dataset_key, body.definition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "definition": saved}


@router.delete("/analysis/metrics")
@limiter.limit("30/minute")
async def remove_semantic_metric(
    request: Request,
    body: SemanticMetricDeleteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    delete_custom_metric(user_id, body.dataset_key, body.metric_key)
    return {"ok": True}


def _require_pro_analytics(user_id: str) -> str:
    tier = str(get_user_tier(user_id) or "free").lower()
    if tier not in {"pro", "premium", "deep"}:
        raise HTTPException(status_code=403, detail="This analysis tool requires Pro/Deep.")
    return tier


def _dax_approval_id(validation: Dict[str, Any], body: DaxPreviewRequest) -> str:
    import hashlib

    material = ":".join((
        str(validation["formula_hash"]), body.dataset_key, body.name, body.mode,
    ))
    return "daxapprove_" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_dax_preview(body: DaxPreviewRequest, user_id: str) -> tuple[Any, Dict[str, Any]]:
    from app.services.dax_engine import validate_dax_expression

    handle = load_handle_from_storage(user_id, body.dataset_key)
    if handle is None:
        raise HTTPException(status_code=404, detail="Dataset not found or unsupported.")
    validation = validate_dax_expression(
        body.expression, columns=handle.column_names(), mode=body.mode,
        governed_relationships=body.governed_relationships,
    )
    if not validation["executable"]:
        raise HTTPException(status_code=400, detail=validation["execution_error"])
    return handle, validation


@router.post("/analysis/dax/validate")
@limiter.limit("60/minute")
async def validate_dax(
    request: Request,
    body: DaxValidateRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.dax_engine import DaxError, validate_dax_expression

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    try:
        return validate_dax_expression(
            body.expression, columns=body.columns, mode=body.mode,
            governed_relationships=body.governed_relationships,
        )
    except DaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/dax/preview")
@limiter.limit("30/minute")
async def preview_dax(
    request: Request,
    body: DaxPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    handle, validation = await asyncio.to_thread(_load_dax_preview, body, user_id)
    compiled = validation["compiled_expression"]
    if body.mode == "measure":
        frame = await asyncio.to_thread(
            handle.execute_select, f'SELECT {compiled} AS "value" FROM df', 2
        )
        preview = {"value": None if frame.empty else frame.iloc[0, 0]}
    else:
        target = '"' + body.name.replace('"', '""') + '"'
        frame = await asyncio.to_thread(
            handle.execute_select,
            f"SELECT {compiled} AS {target} FROM df",
            100,
        )
        series = frame.iloc[:, 0] if not frame.empty else pd.Series(dtype="object")
        preview = {
            "rows": frame.replace({np.nan: None}).to_dict(orient="records"),
            "null_count": int(series.isna().sum()),
            "error_count": 0,
            "distinct_count": int(series.nunique(dropna=True)),
            "distribution": series.describe().replace({np.nan: None}).to_dict() if not series.empty else {},
        }
    return {
        "validation": validation, "preview": preview,
        "approved_action_id": _dax_approval_id(validation, body),
        "action": "preview_dax_definition", "dataset_key": body.dataset_key,
        "name": body.name, "expression": body.expression, "mode": body.mode,
        "requires_confirmation": True,
    }


@router.post("/analysis/dax/publish")
@limiter.limit("15/minute")
async def publish_dax(
    request: Request,
    body: DaxPublishRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.etl_execution import execute_etl_recipe
    from app.services.etl_pipeline import normalize_recipe, recipe_hash

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    _handle, validation = await asyncio.to_thread(_load_dax_preview, body, user_id)
    expected = _dax_approval_id(validation, body)
    if body.approved_action_id != expected:
        raise HTTPException(status_code=409, detail="DAX_CONFIRMATION_HASH_MISMATCH")
    if body.mode == "measure":
        definition = {
            "key": body.name.strip().lower().replace(" ", "_"),
            "label": body.label or body.name,
            "aggregation": "dax_subset",
            "language": "dax_subset_v1",
            "expression": body.expression,
            "normalized_ast": validation["normalized_ast"],
            "compiled_expression": validation["compiled_expression"],
            "dependencies": validation["dependencies"],
            "formula_hash": validation["formula_hash"],
            "output_type": validation["output_type"],
            "description": body.description or "",
            "version": validation["version"],
        }
        saved = await asyncio.to_thread(
            upsert_custom_metric, user_id, body.dataset_key, definition
        )
        return {"ok": True, "kind": "measure", "definition": saved}

    recipe = normalize_recipe({
        "apply": True,
        "transformations": [{
            "type": "dax_calculated", "name": body.name,
            "expression": body.expression,
            "normalized_ast": validation["normalized_ast"],
            "formula_hash": validation["formula_hash"],
            "dependencies": validation["dependencies"],
            "confirmed": True,
        }],
    })
    client = get_supabase_client()
    previous = (
        client.table("etl_recipes").select("version")
        .eq("user_id", user_id).eq("dataset_key", body.dataset_key)
        .order("version", desc=True).limit(1).execute()
    )
    payload = {
        "user_id": user_id, "dataset_key": body.dataset_key,
        "name": f"Calculated column: {body.name}"[:120],
        "version": int(previous.data[0]["version"]) + 1 if previous.data else 1,
        "recipe": recipe, "recipe_hash": recipe_hash(recipe), "is_active": True,
    }
    inserted = client.table("etl_recipes").insert(payload).execute()
    recipe_row = (inserted.data or [payload])[0]
    if not recipe_row.get("id"):
        raise HTTPException(status_code=503, detail="ETL recipe persistence failed.")
    result = await asyncio.to_thread(
        execute_etl_recipe, user_id, recipe_row["id"],
        output_name=f"{body.name}_dataset",
    )
    return {"ok": True, "kind": "calculated_column", "recipe": recipe_row, "dataset_version": result}


@router.post("/analysis/python/proposals")
@limiter.limit("15/minute")
async def create_python_analysis_proposal(
    request: Request,
    body: PythonAnalysisProposalRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.python_sandbox import PythonSandboxError, propose_python_analysis

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    conversation_id = _trusted_conversation_id(user_id, body.conversation_id)
    try:
        return await asyncio.to_thread(
            propose_python_analysis,
            user_id=user_id, conversation_id=conversation_id,
            dataset_key=body.dataset_key,
            dataset_version_hash=body.dataset_version_hash,
            code=body.code, packages=body.packages,
            expected_outputs=body.expected_outputs,
        )
    except PythonSandboxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/python/jobs/{job_id}")
@limiter.limit("120/minute")
async def get_python_analysis_job(
    request: Request,
    job_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.python_sandbox import PythonSandboxError, get_python_job

    _ = request
    _require_pro_analytics(auth_user_id)
    try:
        return await asyncio.to_thread(get_python_job, auth_user_id, job_id)
    except PythonSandboxError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/analysis/python/jobs/{job_id}/confirm")
@limiter.limit("15/minute")
async def confirm_python_analysis_job(
    request: Request,
    job_id: str,
    body: PythonAnalysisConfirmRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.python_sandbox import PythonSandboxError, confirm_python_analysis

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    try:
        return await asyncio.to_thread(
            confirm_python_analysis, user_id, job_id, body.approval_id
        )
    except PythonSandboxError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/analysis/python/jobs/{job_id}/cancel")
@limiter.limit("30/minute")
async def cancel_python_analysis_job(
    request: Request,
    job_id: str,
    body: PythonAnalysisCancelRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.python_sandbox import PythonSandboxError, cancel_python_analysis

    _ = request
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    _require_pro_analytics(user_id)
    try:
        return await cancel_python_analysis(user_id, job_id)
    except PythonSandboxError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _require_user_approved_mapping(chat_request: ChatRequest) -> None:
    """Block every direct dataset path that has no ready Data Setup identity."""
    if chat_request.agent_session_id:
        return
    requires_mapping = bool(
        chat_request.file_attachment_name
        or chat_request.connection_id
    )
    approved_mapping = {
        str(column): str(role).strip()
        for column, role in (chat_request.column_mapping or {}).items()
        if str(role).strip()
    }
    if requires_mapping and (not approved_mapping or not chat_request.data_setup_session_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "ต้องใช้ Dataset Version ที่ผ่าน Data Setup และยืนยัน Mapping แล้ว"
                " ก่อนเริ่มคำนวณและส่งข้อมูลให้ AI"
            ),
        )


def _load_data_setup_session_for_chat(
    chat_request: ChatRequest, user_id: str
) -> Optional[Dict[str, Any]]:
    session_id = str(chat_request.data_setup_session_id or "").strip()
    if not session_id:
        return None
    response = (
        get_supabase_client().table("data_setup_sessions").select("*")
        .eq("id", session_id).eq("user_id", user_id).limit(1).execute()
    )
    return (response.data or [None])[0]


async def _try_conversational_setup_response(
    chat_request: ChatRequest, user_id: str
) -> Optional[ChatResponse]:
    """Phase 5: route non-ready setup sessions through AI Orchestrator when enabled."""
    from app.schemas.chat import Message
    from app.services.orchestrator import (
        orchestrate_workflow_message,
        should_route_to_orchestrator,
    )

    session = _load_data_setup_session_for_chat(chat_request, user_id)
    if not should_route_to_orchestrator(chat_request=chat_request, session=session):
        return None
    assert session is not None
    latest = ""
    for msg in reversed(chat_request.messages or []):
        if getattr(msg, "role", None) and str(msg.role) in {"user", "ChatRole.USER", "USER"}:
            latest = str(msg.content or "")
            break
        if isinstance(msg, dict) and msg.get("role") == "user":
            latest = str(msg.get("content") or "")
            break
    # Message.role may be enum — prefer content of last user message.
    if not latest:
        for msg in reversed(chat_request.messages or []):
            role = getattr(msg, "role", None)
            role_s = getattr(role, "value", role)
            if str(role_s) == "user":
                latest = str(getattr(msg, "content", "") or "")
                break

    from app.services.orchestrator.ui_payload import build_orchestration_ui_payload

    # Prefer structured option clicks; fall back to latest user text.
    resolution = chat_request.orchestration_resolution
    if isinstance(resolution, dict) and resolution.get("decision"):
        decision = str(resolution.get("decision") or "").strip().lower()
        label_map = (
            {
                "approved": "Continue",
                "rejected": "Cancel",
                "modified": "Change settings",
                "approve": "Continue",
                "reject": "Cancel",
                "modify": "Change settings",
            }
            if chat_request.locale == "en"
            else {
                "approved": "ดำเนินการต่อ",
                "rejected": "ไม่ดำเนินการ",
                "modified": "เปลี่ยนการตั้งค่า",
                "approve": "ดำเนินการต่อ",
                "reject": "ไม่ดำเนินการ",
                "modify": "เปลี่ยนการตั้งค่า",
            }
        )
        if decision in label_map and not latest:
            latest = label_map[decision]
        # Normalize aliases used by UI buttons.
        if decision == "approve":
            resolution = {**resolution, "decision": "approved"}
        elif decision == "reject":
            resolution = {**resolution, "decision": "rejected"}
        elif decision == "modify":
            resolution = {**resolution, "decision": "modified"}

    result = await orchestrate_workflow_message(
        session_id=str(session["id"]),
        user_id=user_id,
        message=latest,
        messages=[
            {
                "role": str(getattr(getattr(m, "role", None), "value", getattr(m, "role", ""))),
                "content": str(getattr(m, "content", "") or ""),
            }
            for m in (chat_request.messages or [])
        ],
        tier=str(chat_request.tier or "free"),
        locale=chat_request.locale,
        orchestration_resolution=resolution if isinstance(resolution, dict) else None,
        setup_intent=getattr(chat_request, "setup_intent", None),
        settlement_key=(
            f"orch:{user_id}:{session['id']}:"
            f"{getattr(chat_request, 'client_request_id', None) or latest[:120]}"
        ),
    )
    # Refresh session for ready/source metadata after orchestration.
    refreshed = _load_data_setup_session_for_chat(chat_request, user_id) or session
    orchestration = build_orchestration_ui_payload(result, session=refreshed)
    if result.llm_usage:
        orchestration["llm_usage"] = result.llm_usage
    usage = None
    if result.llm_usage and int(result.llm_usage.get("total_tokens") or 0) > 0:
        from app.schemas.chat import TokenUsage

        usage = TokenUsage(
            prompt_tokens=int(result.llm_usage.get("prompt_tokens") or 0),
            completion_tokens=int(result.llm_usage.get("completion_tokens") or 0),
            total_tokens=int(result.llm_usage.get("total_tokens") or 0),
        )
    return ChatResponse(
        message=Message(role="assistant", content=result.assistant_message),
        model_used=result.model_used or "orchestrator",
        usage=usage,
        agent_paused=getattr(result.decision, "type", None) == "ask_user",
        routing={
            "path": "conversational_data_setup",
            "decision_type": getattr(result.decision, "type", None),
        },
        orchestration=orchestration,
    )


def _require_ready_data_setup(chat_request: ChatRequest, user_id: str) -> None:
    if chat_request.agent_session_id or not (
        chat_request.file_attachment_name or chat_request.connection_id
    ):
        return
    session_id = str(chat_request.data_setup_session_id or "").strip()
    response = (
        get_supabase_client().table("data_setup_sessions").select("*")
        .eq("id", session_id).eq("user_id", user_id).limit(1).execute()
    )
    session = (response.data or [None])[0]
    if not session or session.get("status") != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset Version is not ready. Complete or resume Data Setup first.",
        )
    if chat_request.file_attachment_name != session.get("output_file"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected file does not match the approved Dataset Version.",
        )
    requested_version_id = str(chat_request.dataset_version_id or "").strip()
    session_version_id = str(session.get("dataset_version_id") or "").strip()
    if (
        requested_version_id
        and session_version_id
        and requested_version_id != session_version_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected DatasetVersion does not match the approved session.",
        )
    contract = (session.get("cleaning_recipe") or {}).get("data_contract") or {}
    authoritative_mapping = normalize_mapping(
        session.get("column_mapping")
        or (session.get("cleaning_recipe") or {}).get("column_mapping")
        or {}
    )
    requested_mapping = normalize_mapping(chat_request.column_mapping or {})
    if requested_mapping != authoritative_mapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested Mapping does not match the approved Dataset Version.",
        )
    scan = session.get("scan_result") or {}
    mapping_gate = evaluate_semantic_mapping_gate(
        mapping=authoritative_mapping,
        data_contract=contract,
        columns=scan_columns(scan) or list(authoritative_mapping),
        suggested_mapping=suggested_mapping_from_scan(scan),
        require_confirmation=True,
    )
    if not mapping_gate["ready"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SEMANTIC_MAPPING_REQUIRED",
                "message": "Complete and confirm critical semantic Mapping before analysis.",
                "issues": mapping_gate["issues"],
            },
        )
    if not contract.get("business_context_reviewed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approved Data Contract is incomplete.",
        )
    if chat_request.conversation_id and not session.get("conversation_id"):
        get_supabase_client().table("data_setup_sessions").update({
            "conversation_id": chat_request.conversation_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).eq("user_id", user_id).is_("conversation_id", "null").execute()


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def chat_with_ai(
    request: Request,
    chat_request: ChatRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(chat_request.user_id, auth_user_id)
    try:
        await check_user_message_quota(user_id)
        trusted_tier = get_user_tier(user_id)
        trusted_conversation_id = _trusted_conversation_id(
            user_id, chat_request.conversation_id
        )
        chat_request = chat_request.model_copy(update={
            "user_id": user_id,
            "tier": trusted_tier,
            "conversation_id": trusted_conversation_id,
        })
        orchestrated = await _try_conversational_setup_response(chat_request, user_id)
        if orchestrated is not None:
            return orchestrated

        _require_user_approved_mapping(chat_request)
        _require_ready_data_setup(chat_request, user_id)

        response = await chat_service.get_chat_completion(chat_request)

        if response.usage and not response.agent_paused:
            await record_token_usage(user_id, response.usage.total_tokens)

        return response
    except HTTPException as he:
        # กรณีเป็น Error ที่ส่งมาจาก Quota Service (เช่น 403 Forbidden) ให้ส่งออกไปตรงๆ
        raise he
    except Exception:
        logger.exception("chat_completion_failed", extra={"error_code": "dependency_unavailable"})
        raise

@router.post("/chat/stream")
@limiter.limit("30/minute")
async def chat_with_ai_stream(
    request: Request,
    chat_request: ChatRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(chat_request.user_id, auth_user_id)
    try:
        await check_user_message_quota(user_id)
        trusted_tier = get_user_tier(user_id)
        trusted_conversation_id = _trusted_conversation_id(
            user_id, chat_request.conversation_id
        )
        chat_request = chat_request.model_copy(
            update={
                "user_id": user_id,
                "tier": trusted_tier,
                "conversation_id": trusted_conversation_id,
            }
        )
        orchestrated = await _try_conversational_setup_response(chat_request, user_id)
        if orchestrated is not None:
            async def orchestrated_events():
                import asyncio

                text = orchestrated.message.content or ""
                orchestration_payload = orchestrated.orchestration or {}
                interactive_question = bool(
                    orchestrated.agent_paused
                    and orchestration_payload.get("awaiting_user")
                )
                yield f"data: {json.dumps({'type': 'status', 'stage': 'orchestrator'}, ensure_ascii=False)}\n\n"
                if text and not interactive_question:
                    # Setup answers used to arrive as one large token, so the UI
                    # appeared frozen and then jumped to the full question. Keep
                    # non-interactive narration progressive. Interactive questions
                    # type inside their stable question card on the client instead.
                    chunk_size = max(1, (len(text) + 79) // 80)
                    for offset in range(0, len(text), chunk_size):
                        chunk = text[offset:offset + chunk_size]
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
                        if offset + chunk_size < len(text):
                            await asyncio.sleep(0.018)
                done_payload = {
                    "type": "done",
                    "message": {
                        "role": "assistant",
                        "content": text,
                    },
                    "agent_paused": bool(orchestrated.agent_paused),
                    "model_used": orchestrated.model_used,
                    "routing": orchestrated.routing,
                    "orchestration": orchestrated.orchestration,
                    "usage": (
                        orchestrated.usage.model_dump()
                        if orchestrated.usage is not None
                        else None
                    ),
                }
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                orchestrated_events(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        _require_user_approved_mapping(chat_request)
        _require_ready_data_setup(chat_request, user_id)

        async def event_generator():
            async for chunk in chat_service.stream_chat_completion(chat_request):
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                        if payload.get("type") == "done" and not payload.get("agent_paused"):
                            usage = payload.get("usage") or {}
                            total = usage.get("total_tokens") or 0
                            if total > 0:
                                await record_token_usage(user_id, total)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                yield chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("chat_stream_failed", extra={"error_code": "dependency_unavailable"})
        raise

@router.post("/report/excel")
@limiter.limit("20/minute")
async def generate_excel_report_route(
    request: Request,
    body: ExcelReportRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    import asyncio
    import urllib.parse

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        supabase = get_supabase_client()
        file_name = body.file_attachment_name

        if not file_name:
            try:
                files_list = supabase.storage.from_("business-data").list(user_id)
                if files_list:
                    files_list = sorted(files_list, key=lambda x: x.get("created_at", ""), reverse=True)
                    valid_files = [
                        f for f in files_list
                        if f.get("name", "").lower().endswith((".csv", ".xlsx", ".xls", ".json", ".parquet", ".ndjson"))
                    ]
                    if valid_files:
                        file_name = valid_files[0]["name"]
            except Exception as le:
                logger.warning(
                    "excel_source_fallback_list_failed",
                    extra={"error_code": "source_operation_failed", "error": str(le)},
                )

        if not file_name:
            raise HTTPException(
                status_code=404,
                detail="ไม่พบไฟล์ข้อมูลดิบสำหรับสร้างรายงาน Excel กรุณาอัปโหลดไฟล์หรือซิงค์ข้อมูลใหม่อีกครั้ง",
            )

        target_cols = list(body.column_mapping.keys()) if body.column_mapping else None
        try:
            handle = await asyncio.to_thread(
                load_handle_from_storage,
                user_id,
                file_name,
                target_cols,
            )
        except DatasetLoadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if handle is None:
            raise HTTPException(status_code=400, detail="ไม่รองรับไฟล์นามสกุลนี้สำหรับการสร้างรายงาน Excel")

        cleaning_profile = (body.cleaning_profile or "standard").strip().lower()
        if cleaning_profile not in {"standard", "financial", "conservative", "aggressive"}:
            cleaning_profile = "standard"
        validation_notes, handle = handle.prepare_for_analysis(body.column_mapping or {}, cleaning_profile)
        analytics_results = calculate_analytics_for_handle(
            handle,
            body.column_mapping or {},
            user_id=user_id,
            file_attachment_name=file_name,
            cleaning_profile=cleaning_profile,
            pandas_calculator=chat_service.analytics.calculate,
        )

        total_rows = handle.row_count()
        sample_limit = min(total_rows, REPORT_SAMPLE_ROWS)
        cleaned_df = handle.to_pandas(limit=sample_limit)
        insight = body.summary or ""
        if total_rows > sample_limit:
            insight = (
                f"{insight}\n\n[Data sheet shows first {sample_limit:,} of {total_rows:,} rows; "
                "analytics computed on full dataset.]"
            ).strip()

        excel_buffer = generate_excel_report(
            df=cleaned_df,
            analytics_results=analytics_results,
            insight=insight,
            filename=file_name,
            locale=body.locale or "th",
        )

        safe_filename = urllib.parse.quote(f"{body.title.replace(' ', '_')}.xlsx")

        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"
            },
        )

    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("excel_generation_failed", extra={"error_code": "persistence_failed"})
        raise


class ApiHeaderItem(BaseModel):
    key: str
    value: str = ""


class ApiTestRequest(BaseModel):
    connection_id: Optional[str] = None
    method: str = "GET"
    url: str
    auth_header_name: Optional[str] = None
    auth_header_value: Optional[str] = None
    request_headers: Optional[List[ApiHeaderItem]] = None
    request_body: Optional[Dict[str, Any]] = None


class ApiConnectionWriteRequest(ApiTestRequest):
    name: str = Field(min_length=1, max_length=200)


class DatabaseConnectionWriteRequest(BaseModel):
    provider: str = Field(max_length=40)
    name: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=300)
    port: int = Field(ge=1, le=65535)
    db_name: str = Field(min_length=1, max_length=300)
    username: str = Field(min_length=1, max_length=300)
    password: Optional[str] = Field(default="", max_length=4000)


def _connection_from_api_test(body: ApiTestRequest) -> Dict[str, Any]:
    headers = [
        {"key": item.key, "value": item.value}
        for item in (body.request_headers or [])
        if (item.key or "").strip()
    ]
    if not headers and body.auth_header_name and body.auth_header_value:
        headers = [{"key": body.auth_header_name, "value": body.auth_header_value}]
    return {
        "method": body.method,
        "url": body.url,
        "request_headers": headers,
        "request_body": body.request_body,
        "auth_header_name": body.auth_header_name,
        "auth_header_value": body.auth_header_value,
    }


def _owned_connection(table: str, connection_id: str, user_id: str) -> Dict[str, Any]:
    response = (
        get_supabase_client().table(table).select("*")
        .eq("id", connection_id).eq("user_id", user_id).limit(1).execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Connection not found")
    return response.data[0]


@router.get("/connections")
async def list_external_connections(
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import (
        sanitize_api_connection,
        sanitize_database_connection,
    )

    client = get_supabase_client()
    database = client.table("database_connections").select("*").eq(
        "user_id", auth_user_id
    ).order("created_at", desc=True).execute()
    api = client.table("api_connections").select("*").eq(
        "user_id", auth_user_id
    ).order("created_at", desc=True).execute()
    return {
        "database_connections": [sanitize_database_connection(row) for row in database.data or []],
        "api_connections": [sanitize_api_connection(row) for row in api.data or []],
    }


@router.post("/api-connections")
@limiter.limit("20/minute")
async def create_api_connection(
    request: Request,
    body: ApiConnectionWriteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import api_secret_payload, sanitize_api_connection

    connection = _connection_from_api_test(body)
    fetch_from_connection(connection)
    public_headers = [
        {"key": item["key"], "value": ""} for item in connection["request_headers"]
    ]
    payload = {
        "user_id": auth_user_id,
        "name": body.name.strip(),
        "method": body.method.upper(),
        "url": body.url.strip(),
        "request_headers": public_headers,
        "request_body": None,
        "auth_header_name": connection.get("auth_header_name") or "Authorization",
        "auth_header_value": "",
        "secrets_encrypted": api_secret_payload(connection),
        "secret_version": 1,
        "status": "active",
    }
    response = get_supabase_client().table("api_connections").insert(payload).execute()
    return {"connection": sanitize_api_connection((response.data or [payload])[0])}


@router.put("/api-connections/{connection_id}")
@limiter.limit("20/minute")
async def update_api_connection(
    request: Request,
    connection_id: str,
    body: ApiConnectionWriteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import (
        MASK, api_secret_payload, hydrate_api_connection, sanitize_api_connection,
    )

    current = hydrate_api_connection(_owned_connection("api_connections", connection_id, auth_user_id))
    incoming = _connection_from_api_test(body)
    existing_headers = {
        str(item.get("key") or "").lower(): str(item.get("value") or "")
        for item in current.get("request_headers") or [] if isinstance(item, dict)
    }
    for item in incoming.get("request_headers") or []:
        if item.get("value") == MASK:
            item["value"] = existing_headers.get(str(item.get("key") or "").lower(), "")
    if incoming.get("request_body") is None:
        incoming["request_body"] = current.get("request_body")
    fetch_from_connection(incoming)
    payload = {
        "name": body.name.strip(), "method": body.method.upper(), "url": body.url.strip(),
        "request_headers": [{"key": item["key"], "value": ""} for item in incoming["request_headers"]],
        "request_body": None,
        "auth_header_name": incoming.get("auth_header_name") or "Authorization",
        "auth_header_value": "",
        "secrets_encrypted": api_secret_payload(incoming), "secret_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = get_supabase_client().table("api_connections").update(payload).eq(
        "id", connection_id
    ).eq("user_id", auth_user_id).execute()
    return {"connection": sanitize_api_connection((response.data or [payload])[0])}


@router.post("/api-connections/{connection_id}/test")
@limiter.limit("20/minute")
async def test_saved_api_connection(
    request: Request,
    connection_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import hydrate_api_connection

    fetch_from_connection(hydrate_api_connection(
        _owned_connection("api_connections", connection_id, auth_user_id)
    ))
    return {"status": "success"}


@router.delete("/api-connections/{connection_id}")
async def delete_api_connection(
    connection_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _owned_connection("api_connections", connection_id, auth_user_id)
    get_supabase_client().table("api_connections").delete().eq(
        "id", connection_id
    ).eq("user_id", auth_user_id).execute()
    return {"ok": True}


@router.post("/api-connections/test")
@limiter.limit("20/minute")
async def test_api_connection(
    request: Request,
    body: ApiTestRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    try:
        connection = _connection_from_api_test(body)
        if body.connection_id:
            from app.services.connection_secrets import MASK, hydrate_api_connection

            current = hydrate_api_connection(_owned_connection(
                "api_connections", body.connection_id, auth_user_id
            ))
            existing = {
                str(item.get("key") or "").lower(): str(item.get("value") or "")
                for item in current.get("request_headers") or [] if isinstance(item, dict)
            }
            for item in connection.get("request_headers") or []:
                if item.get("value") == MASK:
                    item["value"] = existing.get(str(item.get("key") or "").lower(), "")
            if connection.get("request_body") is None:
                connection["request_body"] = current.get("request_body")
        fetch_from_connection(connection)
        return {"status": "success", "message": "เชื่อมต่อ API สำเร็จ"}
    except Exception as re:
        raise HTTPException(status_code=400, detail=f"การเชื่อมต่อ API ปลายทางล้มเหลว: {str(re)}")


class ApiSyncRequest(BaseModel):
    connection_id: str
    user_id: str
    overwrite: Optional[bool] = False


class ApiMappingPreviewRequest(BaseModel):
    connection_id: str
    user_id: str
    max_rows: int = 20


@router.post("/api-connections/mapping-preview")
@limiter.limit("20/minute")
async def preview_api_connection_mapping(
    request: Request,
    body: ApiMappingPreviewRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Fetch a bounded API sample for user-approved mapping before analysis."""
    import asyncio

    from app.services.large_data_ingest import ingest_api_connection

    user_id = require_matching_user_id(body.user_id, auth_user_id)
    response = (
        get_supabase_client().from_("api_connections").select("*")
        .eq("id", body.connection_id).eq("user_id", user_id).single().execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลการเชื่อมต่อ API")

    try:
        from app.services.connection_secrets import hydrate_api_connection

        handle = await asyncio.to_thread(
            ingest_api_connection, hydrate_api_connection(response.data)
        )
        if handle is None or handle.row_count() == 0:
            raise HTTPException(status_code=400, detail="API ไม่มีข้อมูลแบบตารางสำหรับจับคู่คอลัมน์")
        frame = handle.to_pandas(limit=max(1, min(body.max_rows, 50)))
        # Pandas timestamps/NaN are normalized to JSON-safe values here.
        rows = json.loads(frame.to_json(orient="records", date_format="iso"))
        return {
            "rows": rows,
            "row_count": handle.row_count(),
            "connection_id": body.connection_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"โหลดตัวอย่าง API เพื่อจับคู่คอลัมน์ไม่สำเร็จ: {exc}",
        ) from exc


@router.post("/api-connections/sync")
@limiter.limit("10/minute")
async def sync_api_connection(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ApiSyncRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        supabase = get_supabase_client()
        res = supabase.from_("api_connections").select("*").eq("id", body.connection_id).eq("user_id", user_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="ไม่พบข้อมูลการเชื่อมต่อ API")
        
        from app.services.connection_secrets import hydrate_api_connection

        conn = hydrate_api_connection(res.data)
        name = conn.get("name", "API_Data")

        import datetime
        import os
        import re
        import tempfile

        from app.services.api_pagination import (
            fetch_connection_json,
            get_pagination_config,
            stream_api_records_to_ndjson,
        )
        from app.services.json_structure import flatten_json_to_records

        ndjson_path = None
        row_count = 0
        try:
            with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as tmp:
                ndjson_path = tmp.name

            if get_pagination_config(conn):
                row_count = stream_api_records_to_ndjson(conn, ndjson_path)
            else:
                try:
                    json_data = fetch_connection_json(conn)
                except Exception as re:
                    raise HTTPException(status_code=400, detail=f"การเชื่อมต่อ API ปลายทางล้มเหลว: {str(re)}") from re
                records = flatten_json_to_records(json_data)
                row_count = len(records) if records else (1 if isinstance(json_data, dict) else 0)
                with open(ndjson_path, "w", encoding="utf-8") as tmp:
                    if records:
                        for rec in records:
                            tmp.write(json.dumps(rec, ensure_ascii=False, default=str))
                            tmp.write("\n")
                    else:
                        tmp.write(json.dumps(json_data, ensure_ascii=False, default=str))
                        tmp.write("\n")
        except HTTPException:
            raise
        except Exception as re:
            raise HTTPException(status_code=400, detail=f"การเชื่อมต่อ API ปลายทางล้มเหลว: {str(re)}") from re

        sanitized_name = name.strip().replace(" ", "_")
        sanitized_name = re.sub(r'[^a-zA-Z0-9.\-_\u0E00-\u0E7F]', '', sanitized_name)

        if body.overwrite:
            filename = f"api_{sanitized_name}.ndjson"
        else:
            timestamp = int(datetime.datetime.now().timestamp())
            filename = f"{timestamp}_api_{sanitized_name}.ndjson"

        file_path = f"{user_id}/{filename}"

        try:
            enforce_customer_storage_quota(
                user_id, os.path.getsize(ndjson_path), file_path if body.overwrite else None
            )
            with open(ndjson_path, "rb") as upload_file:
                supabase.storage.from_("business-data").upload(
                    path=file_path,
                    file=upload_file,
                    file_options={"content-type": "application/x-ndjson", "upsert": "true"},
                )
        except StorageQuotaExceeded as se:
            raise HTTPException(status_code=400, detail=str(se)) from se
        except Exception as se:
            raise HTTPException(status_code=500, detail=f"อัปโหลดไฟล์ไปยังระบบจัดเก็บไม่สำเร็จ: {str(se)}") from se
        finally:
            if ndjson_path and os.path.exists(ndjson_path):
                try:
                    os.unlink(ndjson_path)
                except OSError:
                    pass

        from app.services.etl_scheduler import run_on_upload_schedules

        background_tasks.add_task(run_on_upload_schedules, user_id, filename)
        return {
            "status": "success",
            "filename": filename,
            "message": "ดึงข้อมูลจาก API และบันทึกเรียบร้อยแล้ว",
            "sync_metadata": {
                "row_count": row_count,
                "source": "api",
                "paginated": bool(get_pagination_config(conn)),
            },
        }
        
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("api_sync_failed", extra={"error_code": "source_operation_failed"})
        raise


class DbTestRequest(BaseModel):
    connection_id: Optional[str] = None
    provider: str
    host: str
    port: int
    db_name: str
    username: str
    password: Optional[str] = ""


def _verify_database_connection_payload(body: DbTestRequest) -> None:
    from app.services.sql_execution import (
        build_db_url, create_db_engine, is_supported_db_provider,
    )
    from sqlalchemy import text

    provider = (body.provider or "").lower()
    if not is_supported_db_provider(provider):
        raise HTTPException(status_code=400, detail=f"ไม่รองรับฐานข้อมูลประเภท {provider}")
    db_url = build_db_url(
        provider, body.username, body.password or "", body.host, body.port, body.db_name
    )
    engine = create_db_engine(db_url, provider)
    with engine.connect() as db_conn:
        db_conn.execute(text("SELECT 1"))


@router.post("/db-connections")
@limiter.limit("20/minute")
async def create_database_connection(
    request: Request,
    body: DatabaseConnectionWriteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import encrypt_text, sanitize_database_connection

    _verify_database_connection_payload(DbTestRequest(**body.model_dump()))
    payload = {
        "user_id": auth_user_id, "provider": body.provider.lower(),
        "name": body.name.strip(), "host": body.host.strip(), "port": body.port,
        "db_name": body.db_name.strip(), "username": body.username.strip(),
        "password_encrypted": encrypt_text(body.password or ""), "status": "active",
    }
    response = get_supabase_client().table("database_connections").insert(payload).execute()
    return {"connection": sanitize_database_connection((response.data or [payload])[0])}


@router.put("/db-connections/{connection_id}")
@limiter.limit("20/minute")
async def update_database_connection(
    request: Request,
    connection_id: str,
    body: DatabaseConnectionWriteRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import (
        MASK, encrypt_text, hydrate_database_connection, sanitize_database_connection,
    )

    current_raw = _owned_connection("database_connections", connection_id, auth_user_id)
    current = hydrate_database_connection(current_raw)
    password = current.get("password_encrypted") if body.password in {"", MASK} else body.password
    verified = DbTestRequest(**{**body.model_dump(), "password": password})
    _verify_database_connection_payload(verified)
    payload = {
        "provider": body.provider.lower(), "name": body.name.strip(),
        "host": body.host.strip(), "port": body.port, "db_name": body.db_name.strip(),
        "username": body.username.strip(), "password_encrypted": encrypt_text(password or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = get_supabase_client().table("database_connections").update(payload).eq(
        "id", connection_id
    ).eq("user_id", auth_user_id).execute()
    return {"connection": sanitize_database_connection((response.data or [payload])[0])}


@router.post("/db-connections/{connection_id}/test")
@limiter.limit("20/minute")
async def test_saved_database_connection(
    request: Request,
    connection_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    from app.services.connection_secrets import hydrate_database_connection

    connection = hydrate_database_connection(
        _owned_connection("database_connections", connection_id, auth_user_id)
    )
    _verify_database_connection_payload(DbTestRequest(
        provider=connection.get("provider") or "",
        host=connection.get("host") or "",
        port=int(connection.get("port") or 0),
        db_name=connection.get("db_name") or "",
        username=connection.get("username") or "",
        password=connection.get("password_encrypted") or "",
    ))
    return {"status": "success"}


@router.delete("/db-connections/{connection_id}")
async def delete_database_connection(
    connection_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _owned_connection("database_connections", connection_id, auth_user_id)
    get_supabase_client().table("database_connections").delete().eq(
        "id", connection_id
    ).eq("user_id", auth_user_id).execute()
    return {"ok": True}


@router.post("/db-connections/test")
@limiter.limit("20/minute")
async def test_db_connection(
    request: Request,
    body: DbTestRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    _ = auth_user_id
    try:
        if body.connection_id and body.password in {"", "••••••••"}:
            from app.services.connection_secrets import hydrate_database_connection

            current = hydrate_database_connection(_owned_connection(
                "database_connections", body.connection_id, auth_user_id
            ))
            body = body.model_copy(update={"password": current.get("password_encrypted") or ""})
        try:
            _verify_database_connection_payload(body)
        except Exception as dbe:
            logger.warning(
                "sql_connection_test_rejected",
                extra={"provider": body.provider, "error_code": "source_operation_failed"},
            )
            raise HTTPException(
                status_code=400,
                detail="เชื่อมต่อฐานข้อมูลไม่สำเร็จ กรุณาตรวจสอบ Host, Port, Credential และ Network allowlist",
            ) from dbe
            
        return {"status": "success", "message": "เชื่อมต่อฐานข้อมูลสำเร็จ"}
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("sql_connection_test_failed", extra={"error_code": "source_operation_failed"})
        raise


@router.get("/db-connections/{connection_id}/tables")
async def list_db_connection_tables(
    connection_id: str,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = auth_user_id
    try:
        from app.services.sql_execution import (
            build_db_url,
            create_db_engine,
            is_supported_db_provider,
            list_db_tables,
        )

        supabase = get_supabase_client()
        res = supabase.from_("database_connections").select("*").eq("id", connection_id).eq("user_id", user_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="ไม่พบข้อมูลการเชื่อมต่อฐานข้อมูล")

        from app.services.connection_secrets import hydrate_database_connection

        conn = hydrate_database_connection(res.data)
        provider = (conn.get("provider") or "").lower()
        if not is_supported_db_provider(provider):
            raise HTTPException(status_code=400, detail=f"ไม่รองรับฐานข้อมูลประเภท {provider}")

        db_url = build_db_url(
            provider,
            conn.get("username"),
            conn.get("password_encrypted"),
            conn.get("host"),
            conn.get("port"),
            conn.get("db_name"),
        )
        engine = create_db_engine(db_url, provider)
        tables = list_db_tables(engine, provider)
        return {"status": "success", "tables": tables, "connection_name": conn.get("name", "SQL_DB")}
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("sql_table_discovery_failed", extra={"error_code": "source_operation_failed"})
        raise


class DbSyncRequest(BaseModel):
    connection_id: str
    user_id: str
    query_or_table: str
    overwrite: Optional[bool] = False
    file_format: Optional[str] = "csv" # "csv" | "json"


@router.post("/db-connections/sync")
@limiter.limit("10/minute")
async def sync_db_connection(
    request: Request,
    background_tasks: BackgroundTasks,
    body: DbSyncRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        supabase = get_supabase_client()
        res = supabase.from_("database_connections").select("*").eq("id", body.connection_id).eq("user_id", user_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="ไม่พบข้อมูลการเชื่อมต่อฐานข้อมูล")
            
        from app.services.connection_secrets import hydrate_database_connection

        conn = hydrate_database_connection(res.data)
        provider = (conn.get("provider") or "").lower()
        name = conn.get("name", "DB_Data")

        from app.core.config import settings as app_settings
        from app.services.sql_execution import (
            build_db_url,
            build_select_all_query,
            create_db_engine,
            enforce_row_limit,
            is_supported_db_provider,
            stream_select_to_csv,
        )

        if not is_supported_db_provider(provider):
            raise HTTPException(status_code=400, detail=f"ไม่รองรับฐานข้อมูลประเภท {provider}")

        db_url = build_db_url(
            provider,
            conn.get("username"),
            conn.get("password_encrypted"),
            conn.get("host"),
            conn.get("port"),
            conn.get("db_name"),
        )
            
        query = body.query_or_table.strip()

        if not query.lower().startswith("select"):
            import re
            if not re.match(r"^[a-zA-Z0-9_.]+$", query):
                raise HTTPException(status_code=400, detail="ชื่อตารางไม่ถูกต้อง (อนุญาตเฉพาะตัวอักษร ตัวเลข และ _ เท่านั้น)")
            query = build_select_all_query(query, int(app_settings.SQL_SYNC_ROW_LIMIT))
        else:
            query = enforce_row_limit(query, int(app_settings.SQL_SYNC_ROW_LIMIT))

        import os
        import tempfile

        temp_csv = None
        try:
            engine = create_db_engine(db_url, provider)
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                temp_csv = tmp.name
            row_count = stream_select_to_csv(engine, query, provider, temp_csv)
        except Exception as dbe:
            if temp_csv and os.path.exists(temp_csv):
                try:
                    os.unlink(temp_csv)
                except OSError:
                    pass
            logger.warning(
                "sql_sync_query_rejected",
                extra={"provider": provider, "error_code": "source_operation_failed"},
            )
            raise HTTPException(
                status_code=400,
                detail="การเชื่อมต่อหรือการรันคำสั่ง SQL ล้มเหลว กรุณาตรวจสอบสิทธิ์แบบ read-only และ query",
            ) from dbe
            
        # ล้างอักขระพิเศษสำหรับชื่อไฟล์
        sanitized_name = name.strip().replace(" ", "_")
        import re
        sanitized_name = re.sub(r'[^a-zA-Z0-9.\-_\u0E00-\u0E7F]', '', sanitized_name)
        
        file_format = body.file_format.lower() if body.file_format else "csv"
        if file_format not in ["csv", "json"]:
            file_format = "csv"
            
        if body.overwrite:
            filename = f"db_{sanitized_name}.{file_format}"
        else:
            import datetime
            timestamp = int(datetime.datetime.now().timestamp())
            filename = f"{timestamp}_db_{sanitized_name}.{file_format}"
            
        file_path = f"{user_id}/{filename}"
        
        temp_json = None
        upload_source = temp_csv
        content_type = "text/csv"
        try:
            if file_format != "csv":
                import duckdb

                with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                    temp_json = tmp.name
                esc_csv = temp_csv.replace("'", "''")
                esc_json = temp_json.replace("'", "''")
                con = duckdb.connect()
                con.execute(f"CREATE TABLE sync_data AS SELECT * FROM read_csv_auto('{esc_csv}')")
                con.execute(
                    f"COPY (SELECT * FROM sync_data) TO '{esc_json}' (FORMAT JSON, ARRAY true)"
                )
                upload_source = temp_json
                content_type = "application/json"

            with open(upload_source, "rb") as upload_file:
                enforce_customer_storage_quota(
                    user_id, os.path.getsize(upload_source), file_path if body.overwrite else None
                )
                supabase.storage.from_("business-data").upload(
                    path=file_path,
                    file=upload_file,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
        except StorageQuotaExceeded as se:
            raise HTTPException(status_code=400, detail=str(se)) from se
        except Exception as se:
            raise HTTPException(status_code=500, detail=f"อัปโหลดไฟล์ไปยังระบบจัดเก็บไม่สำเร็จ: {str(se)}")
        finally:
            if temp_csv and os.path.exists(temp_csv):
                try:
                    os.unlink(temp_csv)
                except OSError:
                    pass
            if temp_json and os.path.exists(temp_json):
                try:
                    os.unlink(temp_json)
                except OSError:
                    pass
            
        from app.services.etl_scheduler import run_on_upload_schedules

        background_tasks.add_task(run_on_upload_schedules, user_id, filename)
        return {
            "status": "success",
            "filename": filename,
            "message": f"ดึงข้อมูลจาก SQL และบันทึกเป็นไฟล์ {file_format.upper()} เรียบร้อยแล้ว",
            "sync_metadata": {
                "row_count": row_count,
                "query": query[:500],
                "file_format": file_format,
            },
        }
        
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("sql_sync_failed", extra={"error_code": "source_operation_failed"})
        raise

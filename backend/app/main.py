import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Dict

import io
import pandas as pd
import requests
from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router as chat_router
from app.api.stripe_routes import router as stripe_router
from app.api.customer_routes import router as customer_router
from app.core.auth import get_current_user_id, validate_supabase_storage_url
from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware
from app.core.errors import incident_response
from app.core.observability import (
    bind_correlation_id,
    configure_logging,
    normalize_correlation_id,
    reset_correlation_id,
)
from app.core.parser import detect_and_parse_table
from app.services.file_validation import FileValidationError, validate_upload_bytes
from app.core.rate_limit import limiter
from app.core.schema_ai import suggest_schema
from app.core.analytics import run_modern_analytics
from app.core.insight import generate_insights
from app.services.chat import chat_service
from app.core.supabase import get_supabase_client

configure_logging()
logger = logging.getLogger("mataqorlab.http")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        from app.core.supabase import get_supabase_client
        from app.services.workflow.capability import ensure_workflow_persistence_ready

        ensure_workflow_persistence_ready(get_supabase_client())
    except Exception as exc:
        # Log clearly; production fail-closed is enforced on first workflow use.
        logger.error(
            "workflow_capability_check_failed",
            extra={"error": str(exc)[:300]},
        )
        from app.services.workflow.capability import is_production_env

        if is_production_env():
            raise
    logger.info("api_started", extra={"scheduler_runtime": "external_worker"})
    yield
    logger.info("api_stopped")


app = FastAPI(title="Smart AI Analytics API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            timeout = settings.CHAT_REQUEST_TIMEOUT_SECONDS
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            secs = int(settings.CHAT_REQUEST_TIMEOUT_SECONDS)
            return JSONResponse(
                status_code=504,
                content={"detail": f"Request execution timeout ({secs} seconds exceeded)"},
            )


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = (
            normalize_correlation_id(request.headers.get("X-Correlation-ID"))
            or normalize_correlation_id(request.headers.get("X-Request-ID"))
            or uuid.uuid4().hex
        )
        request.state.correlation_id = request_id
        token = bind_correlation_id(request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error_code": "internal_error",
                },
            )
            response = JSONResponse(
                status_code=500,
                content=incident_response("internal_error", request_id),
            )
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        reset_correlation_id(token)
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TimeoutMiddleware)
app.add_middleware(RequestObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", "Content-Type", "Accept", "X-User-Locale",
        "X-Request-ID", "X-Correlation-ID", "stripe-signature",
    ],
    expose_headers=["X-Request-ID", "X-Correlation-ID", "Server-Timing"],
)

app.include_router(chat_router, prefix="/api/v1")
app.include_router(stripe_router, prefix="/api/v1/stripe", tags=["Stripe"])
app.include_router(
    customer_router,
    prefix="/api/v1/customer-experience",
    tags=["Customer experience"],
)


@app.get("/health/live")
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(request: Request):
    try:
        get_supabase_client().table("plans").select("id", count="exact").limit(1).execute()
    except Exception:
        incident_id = request.state.correlation_id
        logger.exception(
            "readiness_dependency_failed",
            extra={"dependency": "supabase", "error_code": "dependency_unavailable"},
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "dependency": "supabase",
                **incident_response("dependency_unavailable", incident_id),
            },
        )
    return {
        "status": "ready",
        "scheduler_runtime": "external_worker",
        "scheduler_enabled": settings.ETL_SCHEDULER_ENABLED,
        "smart_alert_scheduler_enabled": settings.SMART_ALERT_SCHEDULER_ENABLED,
        "smtp_configured": bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL),
    }


@app.post("/api/upload")
@limiter.limit("30/minute")
async def upload_file(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    file: UploadFile = File(...),
    x_user_locale: str = Header(default="th"),
):
    _ = user_id
    content = await file.read()
    try:
        validate_upload_bytes(file.filename or "upload", len(content))
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    df_info = detect_and_parse_table(content, file.filename)
    schema_suggestions = suggest_schema(df_info["columns"], x_user_locale)

    return {
        "filename": file.filename,
        "locale": x_user_locale,
        "data_preview": df_info["preview"],
        "detected_header_row": df_info["header_row"],
        "schema_suggestions": schema_suggestions,
    }


@app.post("/api/normalize")
@limiter.limit("30/minute")
async def normalize_and_analyze(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    payload: Dict = Body(...),
    x_user_locale: str = Header(default="th"),
):
    _ = user_id
    raw_data = payload.get("data", [])
    mapping = payload.get("mapping", {})

    df = pd.DataFrame(raw_data)
    rename_map = {k: v for k, v in mapping.items() if v}
    normalized_df = df.rename(columns=rename_map)[list(rename_map.values())]

    analytics_results = run_modern_analytics(
        normalized_df,
        mapping,
        pandas_calculator=chat_service.analytics.calculate,
    )
    ai_insight = generate_insights(analytics_results, x_user_locale)

    return {
        "status": "success",
        "normalized_data": normalized_df.to_dict(orient="records"),
        "analytics": analytics_results,
        "insight": ai_insight,
    }


@app.post("/auth/login-event")
@limiter.limit("20/minute")
async def login_event(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    payload: Dict = Body(...),
):
    last_login = payload.get("last_login")
    if last_login:
        try:
            supabase = get_supabase_client()
            supabase.from_("profiles").update({"last_login": last_login}).eq("id", user_id).execute()
        except Exception:
            pass
    return {"status": "ok"}


@app.post("/api/preview-parquet")
@limiter.limit("30/minute")
async def preview_parquet(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    payload: Dict = Body(...),
):
    _ = user_id
    url = payload.get("url")
    validate_supabase_storage_url(url)

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        df = pd.read_parquet(io.BytesIO(response.content))
        preview_df = df.head(100)
        preview_df = preview_df.where(pd.notnull(preview_df), None)

        for col in preview_df.columns:
            if pd.api.types.is_datetime64_any_dtype(preview_df[col]):
                preview_df[col] = preview_df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "status": "success",
            "data": preview_df.to_dict(orient="records"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse Parquet: {str(e)}")

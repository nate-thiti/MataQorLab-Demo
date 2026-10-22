from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from app.core.auth import get_current_user_id, require_matching_user_id
from app.core.rate_limit import limiter
from app.services.stripe_service import StripeService
import logging

router = APIRouter()
logger = logging.getLogger("stripe_routes")

class CheckoutRequest(BaseModel):
    user_id: str
    plan_id: str
    seats: int = Field(default=1, ge=1, le=500)
    organization_name: str | None = Field(default=None, max_length=160)

class CancelSubscriptionRequest(BaseModel):
    user_id: str

@router.post("/cancel-subscription")
@limiter.limit("10/minute")
async def cancel_subscription(
    request: Request,
    body: CancelSubscriptionRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return StripeService.cancel_subscription(user_id=user_id)
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("stripe_cancel_subscription_failed", extra={"error_code": "billing_operation_failed"})
        raise

@router.post("/checkout-session")
@limiter.limit("10/minute")
async def create_checkout_session(
    request: Request,
    body: CheckoutRequest,
    auth_user_id: Annotated[str, Depends(get_current_user_id)],
):
    user_id = require_matching_user_id(body.user_id, auth_user_id)
    try:
        return StripeService.create_checkout_session(
            user_id=user_id,
            plan_id=body.plan_id,
            seats=body.seats,
            organization_name=body.organization_name,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("stripe_checkout_session_failed", extra={"error_code": "billing_operation_failed"})
        raise

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not stripe_signature:
        stripe_signature = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature")

    if not stripe_signature and settings_webhook_secret_exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    payload = await request.body()
    try:
        result = StripeService.process_webhook_payload(payload, stripe_signature)
        return result
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("stripe_webhook_failed", extra={"error_code": "billing_operation_failed"})
        raise

def settings_webhook_secret_exists() -> bool:
    from app.core.config import settings
    return bool(settings.STRIPE_WEBHOOK_SECRET)

import stripe
from app.core.config import settings
from app.core.supabase import get_supabase_client
from fastapi import HTTPException
import logging
import unicodedata

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger("stripe_service")

ENTERPRISE_MIN_SEATS = 2
ENTERPRISE_MAX_SEATS = 500


def _bounded_seat_count(value, *, enterprise: bool) -> int:
    try:
        seats = int(value or 1)
    except (TypeError, ValueError):
        seats = 1
    if not enterprise:
        return 1
    if seats < ENTERPRISE_MIN_SEATS or seats > ENTERPRISE_MAX_SEATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Enterprise requires {ENTERPRISE_MIN_SEATS}-"
                f"{ENTERPRISE_MAX_SEATS} users."
            ),
        )
    return seats


def _required_plan_integer(plan: dict, field: str, *, minimum: int, maximum: int) -> int:
    try:
        value = int(plan.get(field))
    except (TypeError, ValueError):
        value = minimum - 1
    if value < minimum or value > maximum:
        logger.error("Invalid server-owned plan field %s=%r", field, plan.get(field))
        raise HTTPException(
            status_code=500,
            detail="The selected plan has an invalid billing configuration.",
        )
    return value


def _enterprise_checkout_pricing(plan: dict, seat_count: int) -> dict:
    base_price = _required_plan_integer(
        plan,
        "price_monthly",
        minimum=1,
        maximum=100000,
    )
    included_seats = _required_plan_integer(
        plan,
        "included_seats",
        minimum=ENTERPRISE_MIN_SEATS,
        maximum=ENTERPRISE_MAX_SEATS,
    )
    additional_seat_price = _required_plan_integer(
        plan,
        "additional_seat_price_monthly",
        minimum=0,
        maximum=100000,
    )
    additional_seats = max(0, seat_count - included_seats)
    return {
        "base_price": base_price,
        "included_seats": included_seats,
        "additional_seat_price": additional_seat_price,
        "additional_seats": additional_seats,
        "monthly_total": base_price + (additional_seats * additional_seat_price),
    }


def _validated_organization_name(value) -> str:
    raw = str(value or "")
    if any(unicodedata.category(char).startswith("C") for char in raw):
        raise HTTPException(
            status_code=400,
            detail="Organization name contains unsupported characters.",
        )
    name = " ".join(raw.split())
    if len(name) < 2 or len(name) > 160:
        raise HTTPException(
            status_code=400,
            detail=(
                "Enterprise checkout requires an organization name "
                "of 2-160 characters."
            ),
        )
    return name


class StripeService:
    @staticmethod
    def create_checkout_session(
        user_id: str,
        plan_id: str,
        seats: int = 1,
        organization_name: str | None = None,
    ):
        """
        Create a monthly checkout from server-owned plan and profile rows.
        """
        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(
                status_code=500,
                detail="Stripe Secret Key is not configured on the backend."
            )
        try:
            supabase = get_supabase_client()
            profile_res = (
                supabase.table("profiles")
                .select("stripe_customer_id,email")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if not profile_res.data:
                raise HTTPException(status_code=404, detail="User profile not found.")
            profile = profile_res.data[0]
            stripe_customer_id = profile.get("stripe_customer_id")
            email = str(profile.get("email") or "").strip()
            if not stripe_customer_id and not email:
                raise HTTPException(
                    status_code=400,
                    detail="A verified billing email is required.",
                )

            plan_res = (
                supabase.table("plans")
                .select(
                    "id,name,price_monthly,included_seats,"
                    "additional_seat_price_monthly"
                )
                .eq("id", plan_id)
                .limit(1)
                .execute()
            )
            if not plan_res.data:
                raise HTTPException(status_code=404, detail="Plan not found.")
            plan = plan_res.data[0]
            plan_name = str(plan.get("name") or "").strip()
            price_monthly = int(plan.get("price_monthly") or 0)
            if price_monthly <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Paid checkout requires a paid plan.",
                )
            is_enterprise = plan_name.casefold() == "enterprise"
            seat_count = _bounded_seat_count(seats, enterprise=is_enterprise)

            pricing_metadata = {}
            if is_enterprise:
                safe_organization_name = _validated_organization_name(
                    organization_name
                )
                enterprise_pricing = _enterprise_checkout_pricing(plan, seat_count)
                line_items = [{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': (
                                f"{plan_name} Organization - includes "
                                f"{enterprise_pricing['included_seats']} seats"
                            ),
                        },
                        'unit_amount': enterprise_pricing['base_price'] * 100,
                        'recurring': {
                            'interval': 'month',
                        },
                    },
                    'quantity': 1,
                }]
                if enterprise_pricing["additional_seats"] > 0:
                    line_items.append({
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': f"{plan_name} Additional Seat",
                            },
                            'unit_amount': (
                                enterprise_pricing['additional_seat_price'] * 100
                            ),
                            'recurring': {
                                'interval': 'month',
                            },
                        },
                        'quantity': enterprise_pricing["additional_seats"],
                    })
                pricing_metadata = {
                    "included_seats": str(enterprise_pricing["included_seats"]),
                    "additional_seats": str(enterprise_pricing["additional_seats"]),
                    "additional_seat_price_monthly": str(
                        enterprise_pricing["additional_seat_price"]
                    ),
                    "monthly_total": str(enterprise_pricing["monthly_total"]),
                    "pricing_model": "organization_base_plus_additional_seats",
                    "organization_name": safe_organization_name,
                }
            else:
                line_items = [{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': f"{plan_name} Plan - Subscription",
                        },
                        'unit_amount': price_monthly * 100,
                        'recurring': {
                            'interval': 'month',
                        },
                    },
                    'quantity': 1,
                }]

            subscription_metadata = {
                "user_id": user_id,
                "plan_id": plan_id,
                "plan_name": plan_name,
                "seat_count": str(seat_count),
                **pricing_metadata,
            }
            checkout_params = {
                'payment_method_types': ['card'],
                'line_items': line_items,
                'mode': 'subscription',
                'success_url': f"{settings.FRONTEND_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
                'cancel_url': f"{settings.FRONTEND_URL}/dashboard?status=cancelled",
                'subscription_data': {
                    'metadata': subscription_metadata,
                },
                'metadata': subscription_metadata,
                "client_reference_id": user_id,
            }

            if stripe_customer_id:
                checkout_params['customer'] = stripe_customer_id
            else:
                checkout_params['customer_email'] = email

            session = stripe.checkout.Session.create(**checkout_params)
            return {"sessionId": session.id, "url": session.url}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Stripe Session error: {str(e)}")

    @staticmethod
    def process_webhook_payload(payload: bytes, sig_header: str):
        """
        ตรวจสอบ Webhook Signature และอัปเดตข้อมูลการชำระเงิน/แผนใน Supabase
        """
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise HTTPException(
                status_code=503,
                detail="Stripe webhook secret is not configured.",
            )
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            logger.error("Invalid Webhook payload")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as exc:
            logger.error(f"Invalid Webhook signature: {str(exc)}")
            raise HTTPException(status_code=400, detail="Invalid signature")

        event_type = event['type']
        logger.info(f"Received stripe event: {event_type}")

        supabase = get_supabase_client()

        if event_type == "checkout.session.completed":
            session_obj = event['data']['object']
            session = session_obj.to_dict() if hasattr(session_obj, "to_dict") else dict(session_obj)
            metadata = session.get("metadata") or {}
            user_id = metadata.get("user_id")
            plan_id = metadata.get("plan_id")
            stripe_customer_id = session.get("customer")
            stripe_subscription_id = session.get("subscription")

            if user_id and plan_id:
                plan_name = str(metadata.get("plan_name") or "")
                seat_count = _bounded_seat_count(
                    metadata.get("seat_count"),
                    enterprise=plan_name.casefold() == "enterprise",
                )
                # 1. อัปเดตตาราง profiles
                supabase.table("profiles").update({
                    "plan_id": plan_id,
                    "stripe_customer_id": stripe_customer_id,
                    "stripe_subscription_id": stripe_subscription_id,
                    "subscription_status": "active",
                    "subscription_seats": seat_count,
                }).eq("id", user_id).execute()
                logger.info(f"Updated user profile subscription for user_id={user_id} to plan_id={plan_id}")

                if plan_name.casefold() == "enterprise":
                    organization_name = _validated_organization_name(
                        metadata.get("organization_name")
                    )
                    if not stripe_subscription_id:
                        raise HTTPException(
                            status_code=500,
                            detail="Enterprise checkout is missing a Stripe subscription.",
                        )
                    provisioned = supabase.rpc(
                        "provision_enterprise_organization",
                        {
                            "p_user_id": user_id,
                            "p_organization_name": organization_name,
                            "p_stripe_subscription_id": stripe_subscription_id,
                        },
                    ).execute()
                    if not provisioned.data:
                        raise HTTPException(
                            status_code=500,
                            detail="Enterprise organization provisioning failed.",
                        )
                    logger.info(
                        "Provisioned Enterprise organization for user_id=%s",
                        user_id,
                    )

        elif event_type == "invoice.payment_succeeded":
            invoice_obj = event['data']['object']
            invoice = invoice_obj.to_dict() if hasattr(invoice_obj, "to_dict") else dict(invoice_obj)
            stripe_customer_id = invoice.get("customer")
            stripe_subscription_id = invoice.get("subscription")
            amount_paid = invoice.get("amount_paid", 0) / 100.0
            currency = invoice.get("currency")
            stripe_invoice_id = invoice.get("id")
            
            user_id = None
            plan_name = "Plus/Pro"
            seat_count = 1

            # ดึงข้อมูลผู้ใช้จาก stripe_customer_id เพื่อระบุ user_id
            if stripe_customer_id:
                profile_res = supabase.table("profiles").select(
                    "id,plan_id,subscription_seats,plans(name)"
                ).eq("stripe_customer_id", stripe_customer_id).execute()
                if profile_res.data:
                    user_profile = profile_res.data[0]
                    user_id = user_profile.get("id")
                    seat_count = int(user_profile.get("subscription_seats") or 1)
                    
                    # แกะชื่อแผนการใช้งานอย่างปลอดภัย
                    plans_info = user_profile.get("plans")
                    if plans_info:
                        if isinstance(plans_info, list) and len(plans_info) > 0:
                            plan_name = plans_info[0].get("name", "Plus/Pro")
                        elif isinstance(plans_info, dict):
                            plan_name = plans_info.get("name", "Plus/Pro")

            # Subscription metadata is server-authored at checkout and remains the
            # authoritative plan/seat source even when invoice events arrive first.
            if stripe_subscription_id:
                try:
                    subscription = stripe.Subscription.retrieve(stripe_subscription_id)
                    sub_metadata = subscription.get("metadata", {})
                    user_id = sub_metadata.get("user_id") or user_id
                    plan_name = sub_metadata.get("plan_name", plan_name)
                    seat_count = _bounded_seat_count(
                        sub_metadata.get("seat_count"),
                        enterprise=str(plan_name).casefold() == "enterprise",
                    )
                    logger.info(f"Resolved user_id={user_id} and plan_name={plan_name} from Stripe Subscription Metadata fallback")
                except Exception as sub_err:
                    logger.error(f"Error retrieving subscription metadata fallback: {str(sub_err)}")

            if user_id:
                # 2. บันทึกข้อมูลประวัติการชำระเงินลงในตาราง payment_history
                payment_data = {
                    "user_id": user_id,
                    "stripe_invoice_id": stripe_invoice_id,
                    "amount_paid": amount_paid,
                    "currency": currency.upper() if currency else "USD",
                    "payment_status": "paid",
                    "plan_name": plan_name,
                    "seat_count": seat_count,
                }
                try:
                    supabase.table("payment_history").insert(payment_data).execute()
                    logger.info(f"Payment logged successfully for user_id={user_id}, invoice={stripe_invoice_id}")
                except Exception as ie:
                    logger.error(f"Error inserting payment history: {str(ie)}")

        elif event_type == "customer.subscription.deleted":
            subscription_obj = event['data']['object']
            subscription = subscription_obj.to_dict() if hasattr(subscription_obj, "to_dict") else dict(subscription_obj)
            stripe_customer_id = subscription.get("customer")
            
            if stripe_customer_id:
                # อัปเดตสิทธิ์กลับไปเป็น Free แผนเริ่มต้น
                # ค้นหาแผน Free ในตาราง plans
                free_plan_res = supabase.table("plans").select("id").eq("name", "Free").execute()
                free_plan_id = free_plan_res.data[0]["id"] if free_plan_res.data else None
                
                update_data = {
                    "subscription_status": "canceled",
                    "subscription_seats": 1,
                }
                if free_plan_id:
                    update_data["plan_id"] = free_plan_id

                supabase.table("profiles").update(update_data).eq("stripe_customer_id", stripe_customer_id).execute()
                logger.info(f"Canceled subscription for stripe customer_id={stripe_customer_id}")

        return {"status": "success", "event": event_type}

    @staticmethod
    def cancel_subscription(user_id: str):
        """
        ยกเลิกการสมัครสมาชิก (Subscription) ใน Stripe สำหรับ user_id ที่ระบุ
        """
        supabase = get_supabase_client()
        profile_res = supabase.table("profiles").select("stripe_subscription_id").eq("id", user_id).execute()
        if not profile_res.data:
            raise HTTPException(status_code=404, detail="ไม่พบโปรไฟล์ผู้ใช้งาน")
        
        stripe_subscription_id = profile_res.data[0].get("stripe_subscription_id")
        if not stripe_subscription_id:
            raise HTTPException(status_code=400, detail="ผู้ใช้งานนี้ไม่มีการสมัครสมาชิกที่ทำงานอยู่")
        
        try:
            # ลบ subscription ใน Stripe ทันที (จะไป trigger customer.subscription.deleted webhook)
            deleted_sub = stripe.Subscription.delete(stripe_subscription_id)
            return {"status": "success", "message": "ยกเลิกการสมัครสมาชิกสำเร็จ", "subscription": deleted_sub}
        except Exception as e:
            logger.error(f"Error canceling subscription on Stripe: {str(e)}")
            raise HTTPException(status_code=500, detail=f"ไม่สามารถยกเลิกสิทธิ์บน Stripe ได้: {str(e)}")

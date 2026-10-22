from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import stripe_service
from app.services.stripe_service import (
    StripeService,
    _bounded_seat_count,
    _enterprise_checkout_pricing,
    _validated_organization_name,
)


class _Query:
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


class _CheckoutClient:
    def __init__(self, plan):
        self.plan = plan

    def table(self, name):
        if name == "profiles":
            return _Query([{
                "stripe_customer_id": None,
                "email": "owner@example.com",
            }])
        if name == "plans":
            return _Query([self.plan])
        raise AssertionError(f"Unexpected table: {name}")


class _WebhookMutation:
    def __init__(self, client):
        self.client = client

    def update(self, values):
        self.client.profile_updates.append(values)
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"ok": True}])


class _WebhookRpc:
    def execute(self):
        return SimpleNamespace(data={
            "organization_id": "org-1",
            "workspace_id": "workspace-1",
        })


class _WebhookClient:
    def __init__(self):
        self.profile_updates = []
        self.rpc_calls = []

    def table(self, name):
        if name == "profiles":
            return _WebhookMutation(self)
        raise AssertionError(f"Unexpected table: {name}")

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _WebhookRpc()


def test_enterprise_seats_are_bounded():
    assert _bounded_seat_count(2, enterprise=True) == 2
    assert _bounded_seat_count(500, enterprise=True) == 500
    with pytest.raises(HTTPException) as exc:
        _bounded_seat_count(1, enterprise=True)
    assert exc.value.status_code == 400


def test_non_enterprise_checkout_always_uses_one_seat():
    assert _bounded_seat_count(200, enterprise=False) == 1


def test_enterprise_organization_name_is_normalized_and_required():
    assert _validated_organization_name("  MataQor   Labs  ") == "MataQor Labs"
    with pytest.raises(HTTPException) as exc:
        _validated_organization_name(" ")
    assert exc.value.status_code == 400


def test_enterprise_pricing_charges_only_seats_above_included_quantity():
    pricing = _enterprise_checkout_pricing({
        "price_monthly": 99,
        "included_seats": 2,
        "additional_seat_price_monthly": 39,
    }, 5)
    assert pricing == {
        "base_price": 99,
        "included_seats": 2,
        "additional_seat_price": 39,
        "additional_seats": 3,
        "monthly_total": 216,
    }


def test_enterprise_checkout_uses_server_base_and_additional_seat_prices(monkeypatch):
    client = _CheckoutClient({
        "id": "enterprise-plan",
        "name": "Enterprise",
        "price_monthly": 99,
        "included_seats": 2,
        "additional_seat_price_monthly": 39,
    })
    captured = {}

    monkeypatch.setattr(stripe_service.settings, "STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setattr(stripe_service, "get_supabase_client", lambda: client)

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test", url="https://checkout.test/session")

    monkeypatch.setattr(
        stripe_service.stripe.checkout.Session,
        "create",
        fake_create,
    )

    result = StripeService.create_checkout_session(
        user_id="user-1",
        plan_id="enterprise-plan",
        seats=3,
        organization_name="MataQor Labs",
    )

    assert result["sessionId"] == "cs_test"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 9900
    assert captured["line_items"][0]["quantity"] == 1
    assert captured["line_items"][1]["price_data"]["unit_amount"] == 3900
    assert captured["line_items"][1]["quantity"] == 1
    assert captured["metadata"]["seat_count"] == "3"
    assert captured["metadata"]["monthly_total"] == "138"
    assert captured["metadata"]["pricing_model"] == (
        "organization_base_plus_additional_seats"
    )
    assert captured["metadata"]["organization_name"] == "MataQor Labs"
    assert captured["customer_email"] == "owner@example.com"


def test_enterprise_checkout_webhook_provisions_organization(monkeypatch):
    client = _WebhookClient()
    monkeypatch.setattr(stripe_service.settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(stripe_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        stripe_service.stripe.Webhook,
        "construct_event",
        lambda *_args: {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_1",
                    "subscription": "sub_1",
                    "metadata": {
                        "user_id": "00000000-0000-4000-8000-000000000001",
                        "plan_id": "enterprise-plan",
                        "plan_name": "Enterprise",
                        "seat_count": "3",
                        "organization_name": "MataQor Labs",
                    },
                },
            },
        },
    )

    result = StripeService.process_webhook_payload(b"{}", "signature")

    assert result["status"] == "success"
    assert client.profile_updates[0]["subscription_seats"] == 3
    assert client.rpc_calls == [(
        "provision_enterprise_organization",
        {
            "p_user_id": "00000000-0000-4000-8000-000000000001",
            "p_organization_name": "MataQor Labs",
            "p_stripe_subscription_id": "sub_1",
        },
    )]


def test_webhook_fails_closed_without_signing_secret(monkeypatch):
    monkeypatch.setattr(stripe_service.settings, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        StripeService.process_webhook_payload(b"{}", "")
    assert exc.value.status_code == 503


def test_enterprise_migration_has_billing_and_quota_guards():
    sql = (
        Path(__file__).parents[1]
        / "supabase"
        / "enterprise_self_service.sql"
    ).read_text(encoding="utf-8")
    assert "subscription_seats BETWEEN 1 AND 500" in sql
    assert "idx_payment_history_stripe_invoice_unique" in sql
    assert "v_plan_lower LIKE '%enterprise%'" in sql
    assert "v_limit_today := 2000000" in sql


def test_enterprise_base_seat_pricing_migration_is_server_owned():
    sql = (
        Path(__file__).parents[1]
        / "supabase"
        / "enterprise_base_seat_pricing.sql"
    ).read_text(encoding="utf-8")
    assert "included_seats = 2" in sql
    assert "additional_seat_price_monthly = 39" in sql
    assert "price_monthly = 99" in sql


def test_enterprise_business_onboarding_migration_is_private_and_idempotent():
    sql = (
        Path(__file__).parents[1]
        / "supabase"
        / "enterprise_business_onboarding.sql"
    ).read_text(encoding="utf-8")
    assert "private.enterprise_organization_provisioning" in sql
    assert "SECURITY DEFINER" in sql
    assert "Active Enterprise subscription was not verified" in sql
    assert "ON CONFLICT (organization_id, user_id)" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql

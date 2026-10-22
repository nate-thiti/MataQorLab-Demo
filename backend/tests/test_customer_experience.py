from pathlib import Path

import pytest

from app.services.customer_experience import (
    CustomerExperienceError,
    ONBOARDING_STEPS,
    _reject_secret_configuration,
    upsert_integration,
)


def test_customer_integration_metadata_rejects_nested_secrets():
    with pytest.raises(CustomerExperienceError) as exc:
        _reject_secret_configuration({
            "tenant": "example",
            "oauth": {"client_secret": "must-not-be-stored"},
        })
    assert "secret material" in str(exc.value)


def test_customer_integration_metadata_accepts_non_secret_contract():
    _reject_secret_configuration({
        "tenant": "example",
        "setup_required": True,
        "allowed_domains": ["example.com"],
    })


def test_individual_account_cannot_create_organization_only_integration():
    with pytest.raises(CustomerExperienceError, match="requires an organization"):
        upsert_integration(
            "user-1",
            {
                "integration_kind": "sso",
                "provider": "saml",
                "display_name": "SAML SSO",
                "configuration": {"setup_required": True},
            },
            client=object(),
        )


def test_guided_onboarding_covers_the_full_customer_path():
    assert ONBOARDING_STEPS == {
        "profile",
        "sample_data",
        "connect_data",
        "prepare_data",
        "first_analysis",
        "first_dashboard",
        "invite_team",
        "create_alert",
    }


def test_customer_experience_migration_is_backend_only_and_indexed():
    sql = (
        Path(__file__).parents[1]
        / "supabase"
        / "customer_experience_platform.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "customer_onboarding_progress",
        "customer_data_assets",
        "customer_analysis_lineage",
        "customer_collaboration_items",
        "customer_alert_rules",
        "customer_alert_events",
        "customer_integration_settings",
        "customer_organization_invitations",
        "customer_embed_configs",
    ):
        assert f"public.{table}" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
    assert "token_hash TEXT NOT NULL UNIQUE" in sql
    assert "idx_customer_alert_events_rule" in sql
    assert "idx_customer_invites_organization" in sql

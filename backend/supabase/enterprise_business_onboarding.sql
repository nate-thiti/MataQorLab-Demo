-- Atomic, idempotent Enterprise organization provisioning after signed Stripe checkout.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS private;

CREATE TABLE IF NOT EXISTS private.enterprise_organization_provisioning (
    billing_owner_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE RESTRICT,
    organization_id UUID NOT NULL UNIQUE
        REFERENCES public.organizations(id) ON DELETE CASCADE,
    stripe_subscription_id TEXT NOT NULL UNIQUE
        CHECK (char_length(stripe_subscription_id) BETWEEN 1 AND 255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE private.enterprise_organization_provisioning ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE private.enterprise_organization_provisioning
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.provision_enterprise_organization(
    p_user_id UUID,
    p_organization_name TEXT,
    p_stripe_subscription_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_name TEXT := regexp_replace(
        btrim(COALESCE(p_organization_name, '')),
        '[[:space:]]+',
        ' ',
        'g'
    );
    v_subscription_id TEXT := btrim(COALESCE(p_stripe_subscription_id, ''));
    v_slug_base TEXT;
    v_organization_id UUID;
    v_workspace_id UUID;
BEGIN
    IF char_length(v_name) < 2 OR char_length(v_name) > 160 THEN
        RAISE EXCEPTION 'Organization name must contain 2-160 characters';
    END IF;
    IF char_length(v_subscription_id) < 1 OR char_length(v_subscription_id) > 255 THEN
        RAISE EXCEPTION 'Stripe subscription id is required';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.profiles profile
        JOIN public.plans plan ON plan.id = profile.plan_id
        WHERE profile.id = p_user_id
          AND lower(plan.name) = 'enterprise'
          AND profile.subscription_status = 'active'
          AND profile.stripe_subscription_id = v_subscription_id
    ) THEN
        RAISE EXCEPTION 'Active Enterprise subscription was not verified';
    END IF;

    SELECT mapping.organization_id
    INTO v_organization_id
    FROM private.enterprise_organization_provisioning mapping
    WHERE mapping.billing_owner_id = p_user_id
    FOR UPDATE;

    IF v_organization_id IS NULL THEN
        v_slug_base := trim(
            BOTH '-' FROM regexp_replace(lower(v_name), '[^a-z0-9]+', '-', 'g')
        );
        IF char_length(v_slug_base) < 2 THEN
            v_slug_base := 'organization';
        END IF;
        v_slug_base := left(v_slug_base, 52);

        INSERT INTO public.organizations (name, slug, created_by)
        VALUES (
            v_name,
            v_slug_base || '-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8),
            p_user_id
        )
        RETURNING id INTO v_organization_id;

        INSERT INTO private.enterprise_organization_provisioning (
            billing_owner_id,
            organization_id,
            stripe_subscription_id
        )
        VALUES (p_user_id, v_organization_id, v_subscription_id);
    ELSE
        UPDATE private.enterprise_organization_provisioning
        SET
            stripe_subscription_id = v_subscription_id,
            updated_at = now()
        WHERE billing_owner_id = p_user_id;
    END IF;

    INSERT INTO public.organization_members (
        organization_id,
        user_id,
        role,
        status,
        created_by
    )
    VALUES (v_organization_id, p_user_id, 'owner', 'active', p_user_id)
    ON CONFLICT (organization_id, user_id)
    DO UPDATE SET
        role = 'owner',
        status = 'active',
        updated_at = now();

    SELECT workspace.id
    INTO v_workspace_id
    FROM public.workspaces workspace
    WHERE workspace.organization_id = v_organization_id
      AND workspace.slug = 'general'
    FOR UPDATE;

    IF v_workspace_id IS NULL THEN
        INSERT INTO public.workspaces (
            organization_id,
            name,
            slug,
            created_by
        )
        VALUES (v_organization_id, 'General', 'general', p_user_id)
        ON CONFLICT (organization_id, slug)
        DO NOTHING
        RETURNING id INTO v_workspace_id;

        IF v_workspace_id IS NULL THEN
            SELECT workspace.id
            INTO v_workspace_id
            FROM public.workspaces workspace
            WHERE workspace.organization_id = v_organization_id
              AND workspace.slug = 'general';
        END IF;
    END IF;

    INSERT INTO public.workspace_members (
        workspace_id,
        user_id,
        role,
        created_by
    )
    VALUES (v_workspace_id, p_user_id, 'admin', p_user_id)
    ON CONFLICT (workspace_id, user_id)
    DO UPDATE SET role = 'admin';

    RETURN jsonb_build_object(
        'organization_id', v_organization_id,
        'workspace_id', v_workspace_id,
        'role', 'owner',
        'workspace_role', 'admin'
    );
END;
$$;

REVOKE ALL ON FUNCTION public.provision_enterprise_organization(UUID, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.provision_enterprise_organization(UUID, TEXT, TEXT)
    TO service_role;

COMMENT ON TABLE private.enterprise_organization_provisioning IS
    'Private Stripe subscription mapping used for idempotent Enterprise organization provisioning';
COMMENT ON FUNCTION public.provision_enterprise_organization(UUID, TEXT, TEXT) IS
    'Service-role-only atomic provisioning after a verified Enterprise checkout';

-- Customer-facing operating layer for onboarding, health, lineage, collaboration,
-- alerts, organization invitations, integrations and embedded analytics.
-- All writes flow through authenticated FastAPI endpoints using service_role.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.customer_onboarding_progress (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    completed_steps TEXT[] NOT NULL DEFAULT '{}',
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    sample_dataset_loaded BOOLEAN NOT NULL DEFAULT FALSE,
    first_dashboard_id UUID REFERENCES public.visualization_reports(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (completed_steps <@ ARRAY[
        'profile', 'sample_data', 'connect_data', 'prepare_data',
        'first_analysis', 'first_dashboard', 'invite_team', 'create_alert'
    ]::TEXT[])
);

CREATE TABLE IF NOT EXISTS public.customer_data_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    asset_kind TEXT NOT NULL CHECK (
        asset_kind IN ('file', 'api', 'sql', 'cloud', 'dataset')
    ),
    asset_key TEXT NOT NULL CHECK (char_length(asset_key) BETWEEN 1 AND 500),
    display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 240),
    connection_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        connection_status IN ('unknown', 'healthy', 'degraded', 'failed', 'paused')
    ),
    freshness_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        freshness_status IN ('unknown', 'fresh', 'stale', 'expired')
    ),
    quality_score NUMERIC(5,2) CHECK (quality_score BETWEEN 0 AND 100),
    schema_hash TEXT,
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    issue_count INTEGER NOT NULL DEFAULT 0 CHECK (issue_count >= 0),
    issues JSONB NOT NULL DEFAULT '[]'::JSONB CHECK (jsonb_typeof(issues) = 'array'),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(metadata) = 'object'),
    last_checked_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT CHECK (last_error IS NULL OR char_length(last_error) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, asset_kind, asset_key)
);

CREATE TABLE IF NOT EXISTS public.customer_analysis_lineage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    report_id UUID REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL CHECK (char_length(dataset_key) BETWEEN 1 AND 500),
    finding_hash TEXT,
    metric_key TEXT,
    formula TEXT,
    executed_sql TEXT,
    source_refs JSONB NOT NULL DEFAULT '[]'::JSONB
        CHECK (jsonb_typeof(source_refs) = 'array'),
    filter_state JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(filter_state) = 'object'),
    data_version TEXT,
    confidence NUMERIC(4,3) NOT NULL DEFAULT 1
        CHECK (confidence BETWEEN 0 AND 1),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.customer_collaboration_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    report_id UUID NOT NULL REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    item_kind TEXT NOT NULL CHECK (
        item_kind IN ('comment', 'annotation', 'assignment', 'approval')
    ),
    body TEXT NOT NULL DEFAULT '' CHECK (char_length(body) <= 5000),
    anchor JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(anchor) = 'object'),
    assignee_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'resolved', 'approved', 'rejected')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.customer_alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    report_id UUID REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    metric_key TEXT NOT NULL CHECK (char_length(metric_key) BETWEEN 1 AND 160),
    operator TEXT NOT NULL CHECK (
        operator IN ('gt', 'gte', 'lt', 'lte', 'eq', 'change_gt', 'change_lt')
    ),
    threshold NUMERIC,
    channels TEXT[] NOT NULL DEFAULT ARRAY['in_app']::TEXT[] CHECK (
        channels <@ ARRAY['in_app', 'email', 'slack', 'teams', 'webhook']::TEXT[]
        AND cardinality(channels) > 0
    ),
    recipients JSONB NOT NULL DEFAULT '[]'::JSONB
        CHECK (jsonb_typeof(recipients) = 'array'),
    cooldown_minutes INTEGER NOT NULL DEFAULT 60
        CHECK (cooldown_minutes BETWEEN 1 AND 43200),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    muted_until TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ,
    last_triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.customer_alert_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES public.customer_alert_rules(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN ('triggered', 'suppressed', 'delivered', 'acknowledged', 'failed')
    ),
    metric_value NUMERIC,
    previous_value NUMERIC,
    reason TEXT CHECK (reason IS NULL OR char_length(reason) <= 1000),
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(evidence) = 'object'),
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.customer_integration_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    integration_kind TEXT NOT NULL CHECK (
        integration_kind IN ('connector', 'notification', 'sso', 'scim', 'embed')
    ),
    provider TEXT NOT NULL CHECK (char_length(provider) BETWEEN 1 AND 80),
    display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 160),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'ready', 'active', 'error', 'disabled')
    ),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    configuration JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(configuration) = 'object'),
    last_tested_at TIMESTAMPTZ,
    last_error TEXT CHECK (last_error IS NULL OR char_length(last_error) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, integration_kind, provider, display_name)
);

CREATE TABLE IF NOT EXISTS public.customer_organization_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    email TEXT NOT NULL CHECK (
        char_length(email) BETWEEN 3 AND 320 AND email = lower(email)
    ),
    role TEXT NOT NULL DEFAULT 'member' CHECK (
        role IN ('admin', 'reviewer', 'member')
    ),
    token_hash TEXT NOT NULL UNIQUE CHECK (char_length(token_hash) = 64),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'accepted', 'revoked', 'expired')
    ),
    invited_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.customer_embed_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    report_id UUID NOT NULL REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE CHECK (char_length(token_hash) = 64),
    allowed_origins TEXT[] NOT NULL DEFAULT '{}',
    branding JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(branding) = 'object'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'revoked', 'expired')
    ),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customer_assets_user_status
    ON public.customer_data_assets (user_id, connection_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_onboarding_first_dashboard
    ON public.customer_onboarding_progress (first_dashboard_id)
    WHERE first_dashboard_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_assets_organization
    ON public.customer_data_assets (organization_id, updated_at DESC)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_assets_workspace
    ON public.customer_data_assets (workspace_id, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_lineage_user_dataset
    ON public.customer_analysis_lineage (user_id, dataset_key, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_lineage_report
    ON public.customer_analysis_lineage (report_id, computed_at DESC)
    WHERE report_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_lineage_organization
    ON public.customer_analysis_lineage (organization_id)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_lineage_workspace
    ON public.customer_analysis_lineage (workspace_id)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_collaboration_report
    ON public.customer_collaboration_items (report_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_collaboration_user
    ON public.customer_collaboration_items (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_collaboration_organization
    ON public.customer_collaboration_items (organization_id)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_collaboration_workspace
    ON public.customer_collaboration_items (workspace_id)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_collaboration_assignee
    ON public.customer_collaboration_items (assignee_user_id, status)
    WHERE assignee_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_alert_rules_user_enabled
    ON public.customer_alert_rules (user_id, enabled, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_alert_rules_report
    ON public.customer_alert_rules (report_id)
    WHERE report_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_alert_rules_organization
    ON public.customer_alert_rules (organization_id)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_alert_rules_workspace
    ON public.customer_alert_rules (workspace_id)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_alert_events_rule
    ON public.customer_alert_events (rule_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_alert_events_user
    ON public.customer_alert_events (user_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_integrations_user_kind
    ON public.customer_integration_settings (user_id, integration_kind, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_integrations_organization
    ON public.customer_integration_settings (organization_id)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_invites_organization
    ON public.customer_organization_invitations (organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_invites_workspace
    ON public.customer_organization_invitations (workspace_id)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_invites_invited_by
    ON public.customer_organization_invitations (invited_by);
CREATE INDEX IF NOT EXISTS idx_customer_invites_accepted_by
    ON public.customer_organization_invitations (accepted_by)
    WHERE accepted_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_embed_user
    ON public.customer_embed_configs (user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_embed_report
    ON public.customer_embed_configs (report_id, status);
CREATE INDEX IF NOT EXISTS idx_customer_embed_organization
    ON public.customer_embed_configs (organization_id)
    WHERE organization_id IS NOT NULL;

ALTER TABLE public.customer_onboarding_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_data_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_analysis_lineage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_collaboration_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_integration_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_organization_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_embed_configs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
    public.customer_onboarding_progress,
    public.customer_data_assets,
    public.customer_analysis_lineage,
    public.customer_collaboration_items,
    public.customer_alert_rules,
    public.customer_alert_events,
    public.customer_integration_settings,
    public.customer_organization_invitations,
    public.customer_embed_configs
FROM PUBLIC, anon, authenticated;

GRANT ALL ON TABLE
    public.customer_onboarding_progress,
    public.customer_data_assets,
    public.customer_analysis_lineage,
    public.customer_collaboration_items,
    public.customer_alert_rules,
    public.customer_alert_events,
    public.customer_integration_settings,
    public.customer_organization_invitations,
    public.customer_embed_configs
TO service_role;

COMMENT ON TABLE public.customer_onboarding_progress IS
    'Backend-owned guided activation progress for each customer';
COMMENT ON TABLE public.customer_data_assets IS
    'Unified source health, freshness, quality and schema-drift registry';
COMMENT ON TABLE public.customer_analysis_lineage IS
    'Explain-this-number provenance from source and filters through formula or SQL';
COMMENT ON TABLE public.customer_collaboration_items IS
    'Report comments, annotations, assignments and approval decisions';
COMMENT ON TABLE public.customer_alert_rules IS
    'Customer-owned threshold and change alert definitions';
COMMENT ON TABLE public.customer_alert_events IS
    'Immutable alert evaluation and delivery evidence';
COMMENT ON TABLE public.customer_integration_settings IS
    'Non-secret connector, notification, SSO, SCIM and embed configuration metadata';
COMMENT ON TABLE public.customer_organization_invitations IS
    'Hashed, expiring organization invitation lifecycle';
COMMENT ON TABLE public.customer_embed_configs IS
    'Hashed embed access configuration with origin allow-list and branding';

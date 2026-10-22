-- P2 Enterprise Governance: workspace ownership, resource grants,
-- platform/admin audit, job dead letters, and Data Setup approver fields.
-- Apply after organization_workspace_memory.sql and p1_unified_dataset_catalog.sql.

CREATE OR REPLACE FUNCTION private.workspace_role(target_workspace UUID)
RETURNS TEXT
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT member.role
    FROM public.workspace_members member
    WHERE member.workspace_id = target_workspace
      AND member.user_id = (SELECT auth.uid())
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION private.organization_role(target_organization UUID)
RETURNS TEXT
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT member.role
    FROM public.organization_members member
    WHERE member.organization_id = target_organization
      AND member.user_id = (SELECT auth.uid())
      AND member.status = 'active'
    LIMIT 1;
$$;

REVOKE ALL ON FUNCTION private.workspace_role(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.organization_role(UUID) FROM PUBLIC, anon, authenticated;

-- Workspace ownership on the product spine.
ALTER TABLE public.dataset_catalog
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES public.organizations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.dataset_versions
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES public.organizations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.data_setup_sessions
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES public.organizations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES public.workspaces(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_by UUID
        REFERENCES auth.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE public.visualization_reports
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES public.organizations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES public.workspaces(id) ON DELETE SET NULL;
ALTER TABLE public.semantic_metric_definitions
    ADD COLUMN IF NOT EXISTS organization_id UUID
        REFERENCES public.organizations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workspace_id UUID
        REFERENCES public.workspaces(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (approval_status IN ('draft', 'pending', 'approved', 'rejected')),
    ADD COLUMN IF NOT EXISTS approved_by UUID
        REFERENCES auth.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_dataset_catalog_workspace
    ON public.dataset_catalog (workspace_id, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dataset_versions_workspace
    ON public.dataset_versions (workspace_id, version_number DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_workspace
    ON public.data_setup_sessions (workspace_id, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visualization_reports_workspace
    ON public.visualization_reports (workspace_id, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_semantic_metrics_workspace
    ON public.semantic_metric_definitions (workspace_id, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_approved_by
    ON public.data_setup_sessions (approved_by)
    WHERE approved_by IS NOT NULL;

-- Explicit resource grants for org/workspace sharing without weakening owner isolation.
CREATE TABLE IF NOT EXISTS public.resource_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL
        CHECK (resource_type IN (
            'dataset', 'dataset_version', 'data_setup_session',
            'visualization_report', 'semantic_metric', 'etl_recipe'
        )),
    resource_id UUID NOT NULL,
    principal_type TEXT NOT NULL
        CHECK (principal_type IN ('organization', 'workspace', 'user')),
    principal_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    granted_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    UNIQUE (resource_type, resource_id, principal_type, principal_id)
);

CREATE INDEX IF NOT EXISTS idx_resource_grants_principal
    ON public.resource_grants (principal_type, principal_id, resource_type)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_resource_grants_resource
    ON public.resource_grants (resource_type, resource_id)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_resource_grants_org
    ON public.resource_grants (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_grants_workspace
    ON public.resource_grants (workspace_id)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_resource_grants_granted_by
    ON public.resource_grants (granted_by);

ALTER TABLE public.resource_grants ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Members read org resource grants" ON public.resource_grants;
CREATE POLICY "Members read org resource grants"
    ON public.resource_grants FOR SELECT TO authenticated
    USING (private.is_organization_member(organization_id));
REVOKE ALL ON public.resource_grants FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.resource_grants TO authenticated;
GRANT ALL ON public.resource_grants TO service_role;

-- Append-only platform and admin audit trails.
CREATE TABLE IF NOT EXISTS public.platform_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    actor_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 120),
    resource_type TEXT NOT NULL CHECK (char_length(resource_type) BETWEEN 1 AND 80),
    resource_id TEXT,
    correlation_id TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(detail) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.admin_access_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 120),
    target_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    resource_type TEXT,
    resource_id TEXT,
    correlation_id TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(detail) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_platform_audit_org_created
    ON public.platform_audit_events (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_platform_audit_workspace_created
    ON public.platform_audit_events (workspace_id, created_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_platform_audit_actor_created
    ON public.platform_audit_events (actor_user_id, created_at DESC)
    WHERE actor_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_platform_audit_resource
    ON public.platform_audit_events (resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_access_actor_created
    ON public.admin_access_events (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_access_org_created
    ON public.admin_access_events (organization_id, created_at DESC)
    WHERE organization_id IS NOT NULL;

ALTER TABLE public.platform_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_access_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Org members read platform audit" ON public.platform_audit_events;
CREATE POLICY "Org members read platform audit"
    ON public.platform_audit_events FOR SELECT TO authenticated
    USING (
        organization_id IS NOT NULL
        AND private.is_organization_member(organization_id)
        AND private.organization_role(organization_id) IN ('owner', 'admin')
    );
DROP POLICY IF EXISTS "No browser access to admin audit" ON public.admin_access_events;
CREATE POLICY "No browser access to admin audit"
    ON public.admin_access_events FOR ALL TO authenticated
    USING (FALSE) WITH CHECK (FALSE);
REVOKE ALL ON public.platform_audit_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.admin_access_events FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.platform_audit_events TO authenticated;
GRANT ALL ON public.platform_audit_events TO service_role;
GRANT ALL ON public.admin_access_events TO service_role;

-- Failed background jobs for safe replay.
CREATE TABLE IF NOT EXISTS public.job_dead_letters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_kind TEXT NOT NULL CHECK (job_kind IN (
        'data_setup', 'etl_schedule', 'smart_alert', 'weekly_delivery'
    )),
    job_key TEXT NOT NULL,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    error_code TEXT,
    error_message TEXT NOT NULL DEFAULT '' CHECK (char_length(error_message) <= 4000),
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'replaying', 'resolved', 'discarded')),
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_dead_letters_open_unique
    ON public.job_dead_letters (job_kind, job_key)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_job_dead_letters_status_created
    ON public.job_dead_letters (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_dead_letters_kind_status
    ON public.job_dead_letters (job_kind, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_dead_letters_org
    ON public.job_dead_letters (organization_id, created_at DESC)
    WHERE organization_id IS NOT NULL;

ALTER TABLE public.job_dead_letters ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "No browser access to job dead letters" ON public.job_dead_letters;
CREATE POLICY "No browser access to job dead letters"
    ON public.job_dead_letters FOR ALL TO authenticated
    USING (FALSE) WITH CHECK (FALSE);
REVOKE ALL ON public.job_dead_letters FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.job_dead_letters TO service_role;

-- Workspace-aware catalog policies (owner OR workspace member).
DROP POLICY IF EXISTS "Users read own dataset catalog" ON public.dataset_catalog;
CREATE POLICY "Users read accessible dataset catalog"
    ON public.dataset_catalog FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) = user_id
        OR (
            workspace_id IS NOT NULL
            AND private.is_workspace_member(workspace_id)
        )
    );

DROP POLICY IF EXISTS "Users read own dataset versions" ON public.dataset_versions;
CREATE POLICY "Users read accessible dataset versions"
    ON public.dataset_versions FOR SELECT TO authenticated
    USING (
        (SELECT auth.uid()) = user_id
        OR (
            workspace_id IS NOT NULL
            AND private.is_workspace_member(workspace_id)
        )
    );

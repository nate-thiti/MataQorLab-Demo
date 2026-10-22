-- Governed multi-tenant organizations, workspaces and typed company memory.
-- All writes flow through the authenticated FastAPI service; browser roles are read-only.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS private;

CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    slug TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.organization_members (
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'reviewer', 'member')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug),
    UNIQUE (id, organization_id)
);

CREATE TABLE IF NOT EXISTS public.workspace_members (
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer')),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.governed_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope TEXT NOT NULL CHECK (scope IN ('personal', 'organization', 'workspace', 'project', 'dataset')),
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'preference', 'business_definition', 'kpi_formula', 'terminology',
        'policy', 'reporting_convention', 'dataset_fact'
    )),
    memory_key TEXT NOT NULL CHECK (char_length(memory_key) BETWEEN 1 AND 240),
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 240),
    content TEXT NOT NULL DEFAULT '' CHECK (char_length(content) <= 12000),
    structured_value JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(structured_value) = 'object'),
    keywords TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'archived')),
    confidence NUMERIC(4,3) NOT NULL DEFAULT 1
        CHECK (confidence BETWEEN 0 AND 1),
    source_type TEXT NOT NULL DEFAULT 'manual'
        CHECK (source_type IN ('manual', 'verified_finding', 'import', 'correction')),
    source_ref TEXT,
    source_hash TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    supersedes_id UUID REFERENCES public.governed_memories(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    approved_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (scope = 'personal' AND owner_user_id IS NOT NULL AND organization_id IS NULL AND workspace_id IS NULL)
        OR (scope = 'organization' AND organization_id IS NOT NULL AND workspace_id IS NULL AND owner_user_id IS NULL)
        OR (scope IN ('workspace', 'project', 'dataset') AND organization_id IS NOT NULL AND workspace_id IS NOT NULL AND owner_user_id IS NULL)
    ),
    CHECK (
        (status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR status <> 'approved'
    ),
    FOREIGN KEY (workspace_id, organization_id)
        REFERENCES public.workspaces(id, organization_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.governed_memory_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES public.governed_memories(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    snapshot JSONB NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    change_type TEXT NOT NULL CHECK (change_type IN (
        'created', 'updated', 'submitted', 'approved', 'rejected', 'archived', 'restored'
    )),
    changed_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (memory_id, version)
);

CREATE TABLE IF NOT EXISTS public.governed_memory_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID REFERENCES public.governed_memories(id) ON DELETE SET NULL,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    actor_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'created', 'updated', 'submitted', 'approved', 'rejected', 'archived', 'restored', 'retrieved'
    )),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detail) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_org_members_user_active
    ON public.organization_members(user_id, organization_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_organizations_created_by
    ON public.organizations(created_by);
CREATE INDEX IF NOT EXISTS idx_org_members_created_by
    ON public.organization_members(created_by);
CREATE INDEX IF NOT EXISTS idx_workspaces_org_created
    ON public.workspaces(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspaces_created_by
    ON public.workspaces(created_by);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user
    ON public.workspace_members(user_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_created_by
    ON public.workspace_members(created_by);
CREATE INDEX IF NOT EXISTS idx_governed_memories_personal
    ON public.governed_memories(owner_user_id, status, updated_at DESC)
    WHERE scope = 'personal';
CREATE INDEX IF NOT EXISTS idx_governed_memories_org_status
    ON public.governed_memories(organization_id, status, updated_at DESC)
    WHERE organization_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memories_workspace_status
    ON public.governed_memories(workspace_id, status, updated_at DESC)
    WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memories_key
    ON public.governed_memories(memory_key);
CREATE INDEX IF NOT EXISTS idx_governed_memories_created_by
    ON public.governed_memories(created_by);
CREATE INDEX IF NOT EXISTS idx_governed_memories_approved_by
    ON public.governed_memories(approved_by) WHERE approved_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memories_supersedes
    ON public.governed_memories(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memory_revisions_org_created
    ON public.governed_memory_revisions(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_governed_memory_audit_org_created
    ON public.governed_memory_audit_events(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_governed_memory_audit_actor
    ON public.governed_memory_audit_events(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_governed_memory_revisions_owner
    ON public.governed_memory_revisions(owner_user_id, created_at DESC)
    WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memory_revisions_changed_by
    ON public.governed_memory_revisions(changed_by);
CREATE INDEX IF NOT EXISTS idx_governed_memory_audit_memory
    ON public.governed_memory_audit_events(memory_id) WHERE memory_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_governed_memory_audit_owner
    ON public.governed_memory_audit_events(owner_user_id, created_at DESC)
    WHERE owner_user_id IS NOT NULL;

CREATE OR REPLACE FUNCTION private.is_organization_member(target_organization UUID)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.organization_members member
        WHERE member.organization_id = target_organization
          AND member.user_id = (SELECT auth.uid())
          AND member.status = 'active'
    );
$$;

CREATE OR REPLACE FUNCTION private.is_workspace_member(target_workspace UUID)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.workspace_members member
        WHERE member.workspace_id = target_workspace
          AND member.user_id = (SELECT auth.uid())
    );
$$;

REVOKE ALL ON FUNCTION private.is_organization_member(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.is_workspace_member(UUID) FROM PUBLIC, anon, authenticated;

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.governed_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.governed_memory_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.governed_memory_audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Members read organizations" ON public.organizations
    FOR SELECT TO authenticated USING ((SELECT private.is_organization_member(id)));
CREATE POLICY "Members read organization memberships" ON public.organization_members
    FOR SELECT TO authenticated USING ((SELECT private.is_organization_member(organization_id)));
CREATE POLICY "Members read workspaces" ON public.workspaces
    FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(id)));
CREATE POLICY "Members read workspace memberships" ON public.workspace_members
    FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));
CREATE POLICY "Users read governed memories" ON public.governed_memories
    FOR SELECT TO authenticated USING (
        (scope = 'personal' AND owner_user_id = (SELECT auth.uid()))
        OR (
            status = 'approved'
            AND organization_id IS NOT NULL
            AND (SELECT private.is_organization_member(organization_id))
            AND (workspace_id IS NULL OR (SELECT private.is_workspace_member(workspace_id)))
        )
    );
CREATE POLICY "Users read governed memory revisions" ON public.governed_memory_revisions
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM public.governed_memories memory
            WHERE memory.id = memory_id
              AND (
                (memory.scope = 'personal' AND memory.owner_user_id = (SELECT auth.uid()))
                OR (
                    memory.status = 'approved'
                    AND (SELECT private.is_organization_member(memory.organization_id))
                    AND (
                        memory.workspace_id IS NULL
                        OR (SELECT private.is_workspace_member(memory.workspace_id))
                    )
                )
              )
        )
    );
CREATE POLICY "Members read governed memory audit" ON public.governed_memory_audit_events
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM public.governed_memories memory
            WHERE memory.id = memory_id
              AND (
                (memory.scope = 'personal' AND memory.owner_user_id = (SELECT auth.uid()))
                OR (
                    memory.status = 'approved'
                    AND (SELECT private.is_organization_member(memory.organization_id))
                    AND (
                        memory.workspace_id IS NULL
                        OR (SELECT private.is_workspace_member(memory.workspace_id))
                    )
                )
              )
        )
    );

REVOKE ALL ON TABLE public.organizations, public.organization_members,
    public.workspaces, public.workspace_members, public.governed_memories,
    public.governed_memory_revisions, public.governed_memory_audit_events
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.organizations, public.organization_members,
    public.workspaces, public.workspace_members, public.governed_memories,
    public.governed_memory_revisions, public.governed_memory_audit_events
    TO authenticated;
GRANT ALL ON TABLE public.organizations, public.organization_members,
    public.workspaces, public.workspace_members, public.governed_memories,
    public.governed_memory_revisions, public.governed_memory_audit_events
    TO service_role;

COMMENT ON TABLE public.governed_memories IS
    'Typed, versioned personal and company context; shared records require reviewer approval before retrieval';

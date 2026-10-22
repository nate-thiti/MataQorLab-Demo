-- Visualization revision history and revocable read-only share links.
-- Apply after dynamic_visualization_dashboards.sql.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.visualization_dashboard_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dashboard_spec JSONB NOT NULL CHECK (jsonb_typeof(dashboard_spec) = 'object'),
    change_summary TEXT NOT NULL DEFAULT '' CHECK (char_length(change_summary) <= 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.visualization_report_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    allow_detail_rows BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS public.visualization_dashboard_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    dashboard_spec JSONB NOT NULL CHECK (jsonb_typeof(dashboard_spec) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visualization_revisions_report_created
    ON public.visualization_dashboard_revisions(report_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visualization_revisions_user_created
    ON public.visualization_dashboard_revisions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visualization_shares_report_created
    ON public.visualization_report_shares(report_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visualization_shares_user_created
    ON public.visualization_report_shares(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visualization_shares_active_token
    ON public.visualization_report_shares(token)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_visualization_templates_user_updated
    ON public.visualization_dashboard_templates(user_id, updated_at DESC);

ALTER TABLE public.visualization_dashboard_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visualization_report_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visualization_dashboard_templates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Owners can read visualization revisions"
    ON public.visualization_dashboard_revisions;
CREATE POLICY "Owners can read visualization revisions"
    ON public.visualization_dashboard_revisions FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can create visualization revisions"
    ON public.visualization_dashboard_revisions;
CREATE POLICY "Owners can create visualization revisions"
    ON public.visualization_dashboard_revisions FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM public.visualization_reports report
            WHERE report.id = report_id
              AND report.user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "Owners can delete visualization revisions"
    ON public.visualization_dashboard_revisions;
CREATE POLICY "Owners can delete visualization revisions"
    ON public.visualization_dashboard_revisions FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can read visualization shares"
    ON public.visualization_report_shares;
CREATE POLICY "Owners can read visualization shares"
    ON public.visualization_report_shares FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can create visualization shares"
    ON public.visualization_report_shares;
CREATE POLICY "Owners can create visualization shares"
    ON public.visualization_report_shares FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM public.visualization_reports report
            WHERE report.id = report_id
              AND report.user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "Owners can update visualization shares"
    ON public.visualization_report_shares;

DROP POLICY IF EXISTS "Owners can delete visualization shares"
    ON public.visualization_report_shares;
CREATE POLICY "Owners can delete visualization shares"
    ON public.visualization_report_shares FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can manage visualization templates"
    ON public.visualization_dashboard_templates;
CREATE POLICY "Owners can manage visualization templates"
    ON public.visualization_dashboard_templates FOR ALL TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

REVOKE ALL ON TABLE
    public.visualization_dashboard_revisions,
    public.visualization_report_shares,
    public.visualization_dashboard_templates
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, DELETE ON TABLE public.visualization_dashboard_revisions
    TO authenticated, service_role;
GRANT SELECT, INSERT, DELETE ON TABLE public.visualization_report_shares
    TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.visualization_dashboard_revisions,
    public.visualization_report_shares,
    public.visualization_dashboard_templates
    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.visualization_dashboard_templates
    TO authenticated, service_role;

COMMENT ON TABLE public.visualization_dashboard_revisions IS
    'Immutable owner-scoped snapshots created before a dashboard specification is replaced';
COMMENT ON TABLE public.visualization_report_shares IS
    'Owner-managed, revocable opaque tokens resolved only by the backend share endpoint';
COMMENT ON TABLE public.visualization_dashboard_templates IS
    'Owner-scoped reusable dashboard specifications validated again against each target dataset';

-- Owner-scoped Visualization reports and chart snapshots.
-- Apply after customer_storage_quota.sql so the final function also counts these rows.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.visualization_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    description TEXT NOT NULL DEFAULT '' CHECK (char_length(description) <= 4000),
    executive_summary TEXT NOT NULL DEFAULT '' CHECK (char_length(executive_summary) <= 20000),
    dataset_key TEXT CHECK (dataset_key IS NULL OR char_length(dataset_key) <= 500),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final')),
    created_via TEXT NOT NULL DEFAULT 'workspace'
        CHECK (created_via IN ('workspace', 'chat', 'ai')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.visualization_charts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES public.visualization_reports(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_message_id UUID REFERENCES public.chat_messages(id) ON DELETE SET NULL,
    chart_type TEXT NOT NULL CHECK (chart_type IN ('bar', 'line', 'area', 'pie')),
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    subtitle TEXT NOT NULL DEFAULT '' CHECK (char_length(subtitle) <= 1000),
    config JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config) = 'object'),
    data JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(data) = 'array'),
    insight TEXT NOT NULL DEFAULT '' CHECK (char_length(insight) <= 10000),
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visualization_reports_user_updated
    ON public.visualization_reports(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_visualization_reports_conversation
    ON public.visualization_reports(conversation_id)
    WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visualization_charts_report_order
    ON public.visualization_charts(report_id, sort_order, created_at);
CREATE INDEX IF NOT EXISTS idx_visualization_charts_user
    ON public.visualization_charts(user_id);
CREATE INDEX IF NOT EXISTS idx_visualization_charts_source_message
    ON public.visualization_charts(source_message_id)
    WHERE source_message_id IS NOT NULL;

ALTER TABLE public.visualization_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visualization_charts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Owners can read visualization reports" ON public.visualization_reports;
CREATE POLICY "Owners can read visualization reports"
    ON public.visualization_reports FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can create visualization reports" ON public.visualization_reports;
CREATE POLICY "Owners can create visualization reports"
    ON public.visualization_reports FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND (
            conversation_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.conversations c
                WHERE c.id = conversation_id AND c.user_id = (SELECT auth.uid())
            )
        )
    );

DROP POLICY IF EXISTS "Owners can update visualization reports" ON public.visualization_reports;
CREATE POLICY "Owners can update visualization reports"
    ON public.visualization_reports FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND (
            conversation_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.conversations c
                WHERE c.id = conversation_id AND c.user_id = (SELECT auth.uid())
            )
        )
    );

DROP POLICY IF EXISTS "Owners can delete visualization reports" ON public.visualization_reports;
CREATE POLICY "Owners can delete visualization reports"
    ON public.visualization_reports FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can read visualization charts" ON public.visualization_charts;
CREATE POLICY "Owners can read visualization charts"
    ON public.visualization_charts FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Owners can create visualization charts" ON public.visualization_charts;
CREATE POLICY "Owners can create visualization charts"
    ON public.visualization_charts FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND EXISTS (
            SELECT 1
            FROM public.visualization_reports r
            WHERE r.id = report_id AND r.user_id = (SELECT auth.uid())
        )
        AND (
            source_message_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.chat_messages m
                WHERE m.id = source_message_id AND m.user_id = (SELECT auth.uid())
            )
        )
    );

DROP POLICY IF EXISTS "Owners can update visualization charts" ON public.visualization_charts;
CREATE POLICY "Owners can update visualization charts"
    ON public.visualization_charts FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND EXISTS (
            SELECT 1
            FROM public.visualization_reports r
            WHERE r.id = report_id AND r.user_id = (SELECT auth.uid())
        )
        AND (
            source_message_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.chat_messages m
                WHERE m.id = source_message_id AND m.user_id = (SELECT auth.uid())
            )
        )
    );

DROP POLICY IF EXISTS "Owners can delete visualization charts" ON public.visualization_charts;
CREATE POLICY "Owners can delete visualization charts"
    ON public.visualization_charts FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

REVOKE ALL ON TABLE public.visualization_reports FROM PUBLIC, anon;
REVOKE ALL ON TABLE public.visualization_charts FROM PUBLIC, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.visualization_reports
    TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.visualization_charts
    TO authenticated, service_role;

-- Keep Visualization configuration inside the same customer-owned storage total.
CREATE OR REPLACE FUNCTION private.customer_storage_usage(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
  v_storage bigint := 0;
  v_database bigint := 0;
  v_limit bigint := 0;
BEGIN
  SELECT COALESCE(sum((o.metadata->>'size')::bigint), 0)
  INTO v_storage
  FROM storage.objects o
  WHERE (o.bucket_id = 'business-data' AND (storage.foldername(o.name))[1] = p_user_id::text)
     OR (o.bucket_id = 'avatars' AND (storage.foldername(o.name))[1] = p_user_id::text);

  SELECT
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.profiles r WHERE r.id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.conversations r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_messages r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_memories r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_quality_events r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.database_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.api_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.payment_history r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.agent_sessions r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.cloud_dataset_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_recipes r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_pipeline_runs r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_schedules r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_quality_alerts r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.analysis_insights_memory r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.column_mappings_memory r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.semantic_metric_definitions r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.visualization_reports r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.visualization_charts r WHERE r.user_id = p_user_id), 0)
  INTO v_database;

  SELECT COALESCE(pl.storage_limit_mb, 1)::bigint * 1024 * 1024
  INTO v_limit
  FROM public.profiles pr
  LEFT JOIN public.plans pl ON pl.id = pr.plan_id
  WHERE pr.id = p_user_id;

  v_limit := COALESCE(v_limit, 1024 * 1024);
  RETURN jsonb_build_object(
    'storage_bytes', v_storage,
    'database_bytes', v_database,
    'used_bytes', v_storage + v_database,
    'limit_bytes', v_limit,
    'remaining_bytes', greatest(0, v_limit - v_storage - v_database)
  );
END;
$$;

REVOKE ALL ON FUNCTION private.customer_storage_usage(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.customer_storage_usage(uuid) TO service_role;

COMMENT ON TABLE public.visualization_reports IS
    'Private user-owned report workspaces created from chat analysis or the Visualization page';
COMMENT ON TABLE public.visualization_charts IS
    'Immutable chart data snapshots attached to a private Visualization report';

-- Linked Google/Microsoft tabular sources. Source binaries remain at the provider.
CREATE TABLE IF NOT EXISTS public.cloud_dataset_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
    display_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    provider_file_id TEXT,
    sheet_name TEXT,
    json_path TEXT,
    etag TEXT,
    content_hash TEXT,
    file_type TEXT,
    size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    last_modified TEXT,
    last_synced_at TIMESTAMPTZ,
    last_status TEXT NOT NULL DEFAULT 'never'
        CHECK (last_status IN ('never', 'syncing', 'unchanged', 'completed', 'failed')),
    last_error TEXT,
    latest_output_file TEXT,
    recipe_id UUID REFERENCES public.etl_recipes(id) ON DELETE SET NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cloud_dataset_connections_user
    ON public.cloud_dataset_connections (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cloud_dataset_connections_recipe
    ON public.cloud_dataset_connections (recipe_id);

ALTER TABLE public.cloud_dataset_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cloud_dataset_connections_select_owner" ON public.cloud_dataset_connections;
CREATE POLICY "cloud_dataset_connections_select_owner"
ON public.cloud_dataset_connections FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "cloud_dataset_connections_insert_owner" ON public.cloud_dataset_connections;
CREATE POLICY "cloud_dataset_connections_insert_owner"
ON public.cloud_dataset_connections FOR INSERT TO authenticated
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "cloud_dataset_connections_update_owner" ON public.cloud_dataset_connections;
CREATE POLICY "cloud_dataset_connections_update_owner"
ON public.cloud_dataset_connections FOR UPDATE TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "cloud_dataset_connections_delete_owner" ON public.cloud_dataset_connections;
CREATE POLICY "cloud_dataset_connections_delete_owner"
ON public.cloud_dataset_connections FOR DELETE TO authenticated
USING ((SELECT auth.uid()) = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.cloud_dataset_connections TO authenticated;
GRANT ALL ON public.cloud_dataset_connections TO service_role;

COMMENT ON TABLE public.cloud_dataset_connections IS
    'Owner-scoped Google Drive/Sheets and Microsoft OneDrive/SharePoint links; source binaries are fetched transiently';

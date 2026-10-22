-- Unified Dataset Catalog, immutable DatasetVersion records, and lineage.
-- Apply after etl_workflows.sql, adaptive_data_setup_copilot.sql, and
-- p0_data_flow_security_hardening.sql.

ALTER TABLE public.data_setup_sessions
    DROP CONSTRAINT IF EXISTS data_setup_sessions_source_type_check;
ALTER TABLE public.data_setup_sessions
    ADD CONSTRAINT data_setup_sessions_source_type_check
    CHECK (source_type IN ('file', 'api', 'sql', 'cloud'));

CREATE TABLE IF NOT EXISTS public.dataset_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    canonical_dataset_key TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('file', 'api', 'sql', 'cloud')),
    source_ref JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(source_ref) = 'object'),
    display_name TEXT NOT NULL,
    active_version_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, canonical_dataset_key)
);

CREATE TABLE IF NOT EXISTS public.dataset_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    catalog_id UUID NOT NULL REFERENCES public.dataset_catalog(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('processing', 'ready', 'failed', 'superseded')),
    source_fingerprint TEXT,
    recipe_hash TEXT,
    contract_hash TEXT,
    recipe_id UUID REFERENCES public.etl_recipes(id) ON DELETE SET NULL,
    run_id UUID REFERENCES public.etl_pipeline_runs(id) ON DELETE SET NULL,
    data_setup_session_id UUID REFERENCES public.data_setup_sessions(id) ON DELETE SET NULL,
    output_dataset_key TEXT NOT NULL,
    output_file TEXT NOT NULL,
    output_version TEXT,
    materialized_prepared BOOLEAN NOT NULL DEFAULT TRUE,
    lineage JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(lineage) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (catalog_id, version_number)
);

ALTER TABLE public.dataset_catalog
    DROP CONSTRAINT IF EXISTS dataset_catalog_active_version_id_fkey;
ALTER TABLE public.dataset_catalog
    ADD CONSTRAINT dataset_catalog_active_version_id_fkey
    FOREIGN KEY (active_version_id) REFERENCES public.dataset_versions(id) ON DELETE SET NULL;

ALTER TABLE public.data_setup_sessions
    ADD COLUMN IF NOT EXISTS dataset_version_id UUID
    REFERENCES public.dataset_versions(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_versions_run
    ON public.dataset_versions (run_id)
    WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dataset_catalog_user_updated
    ON public.dataset_catalog (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_catalog_active_version
    ON public.dataset_catalog (active_version_id)
    WHERE active_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dataset_versions_catalog_created
    ON public.dataset_versions (catalog_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_user_output
    ON public.dataset_versions (user_id, output_dataset_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_recipe
    ON public.dataset_versions (recipe_id)
    WHERE recipe_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dataset_versions_data_setup
    ON public.dataset_versions (data_setup_session_id)
    WHERE data_setup_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_dataset_version
    ON public.data_setup_sessions (dataset_version_id)
    WHERE dataset_version_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.dataset_lineage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_version_id UUID NOT NULL REFERENCES public.dataset_versions(id) ON DELETE CASCADE,
    event_kind TEXT NOT NULL
        CHECK (event_kind IN (
            'published', 'chat_analysis', 'dashboard_created',
            'dashboard_viewed', 'exported'
        )),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dataset_lineage_version_created
    ON public.dataset_lineage_events (dataset_version_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dataset_lineage_user_created
    ON public.dataset_lineage_events (user_id, created_at DESC);

ALTER TABLE public.dataset_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dataset_lineage_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own dataset catalog" ON public.dataset_catalog;
CREATE POLICY "Users read own dataset catalog"
    ON public.dataset_catalog FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users read own dataset versions" ON public.dataset_versions;
CREATE POLICY "Users read own dataset versions"
    ON public.dataset_versions FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users read own dataset lineage" ON public.dataset_lineage_events;
CREATE POLICY "Users read own dataset lineage"
    ON public.dataset_lineage_events FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

REVOKE ALL ON public.dataset_catalog FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.dataset_versions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.dataset_lineage_events FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.dataset_catalog TO authenticated;
GRANT SELECT ON public.dataset_versions TO authenticated;
GRANT SELECT ON public.dataset_lineage_events TO authenticated;
GRANT ALL ON public.dataset_catalog TO service_role;
GRANT ALL ON public.dataset_versions TO service_role;
GRANT ALL ON public.dataset_lineage_events TO service_role;

CREATE OR REPLACE FUNCTION public.register_dataset_version(
    p_user_id UUID,
    p_canonical_dataset_key TEXT,
    p_source_type TEXT,
    p_source_ref JSONB,
    p_display_name TEXT,
    p_source_fingerprint TEXT,
    p_recipe_hash TEXT,
    p_contract_hash TEXT,
    p_recipe_id UUID,
    p_run_id UUID,
    p_data_setup_session_id UUID,
    p_output_dataset_key TEXT,
    p_output_file TEXT,
    p_output_version TEXT,
    p_lineage JSONB
)
RETURNS SETOF public.dataset_versions
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_catalog_id UUID;
    v_version_id UUID;
    v_version_number INTEGER;
BEGIN
    IF p_source_type NOT IN ('file', 'api', 'sql', 'cloud') THEN
        RAISE EXCEPTION 'Unsupported dataset source type';
    END IF;

    INSERT INTO public.dataset_catalog (
        user_id, canonical_dataset_key, source_type, source_ref, display_name
    )
    VALUES (
        p_user_id,
        p_canonical_dataset_key,
        p_source_type,
        COALESCE(p_source_ref, '{}'::jsonb),
        p_display_name
    )
    ON CONFLICT (user_id, canonical_dataset_key) DO UPDATE SET
        source_type = EXCLUDED.source_type,
        source_ref = EXCLUDED.source_ref,
        display_name = EXCLUDED.display_name,
        updated_at = now()
    RETURNING id INTO v_catalog_id;

    PERFORM 1
    FROM public.dataset_catalog
    WHERE id = v_catalog_id
    FOR UPDATE;

    IF p_run_id IS NOT NULL THEN
        SELECT id INTO v_version_id
        FROM public.dataset_versions
        WHERE run_id = p_run_id;
    END IF;

    IF v_version_id IS NULL THEN
        SELECT COALESCE(MAX(version_number), 0) + 1
        INTO v_version_number
        FROM public.dataset_versions
        WHERE catalog_id = v_catalog_id;

        INSERT INTO public.dataset_versions (
            user_id, catalog_id, version_number, status,
            source_fingerprint, recipe_hash, contract_hash,
            recipe_id, run_id, data_setup_session_id,
            output_dataset_key, output_file, output_version,
            materialized_prepared, lineage, completed_at
        )
        VALUES (
            p_user_id, v_catalog_id, v_version_number, 'ready',
            p_source_fingerprint, p_recipe_hash, p_contract_hash,
            p_recipe_id, p_run_id, p_data_setup_session_id,
            p_output_dataset_key, p_output_file, p_output_version,
            TRUE, COALESCE(p_lineage, '{}'::jsonb), now()
        )
        RETURNING id INTO v_version_id;

        UPDATE public.dataset_versions
        SET status = 'superseded'
        WHERE catalog_id = v_catalog_id
          AND id <> v_version_id
          AND status = 'ready';

        INSERT INTO public.dataset_lineage_events (
            user_id, dataset_version_id, event_kind, payload
        )
        VALUES (
            p_user_id,
            v_version_id,
            'published',
            jsonb_build_object(
                'run_id', p_run_id,
                'source_type', p_source_type,
                'output_dataset_key', p_output_dataset_key
            )
        );
    END IF;

    UPDATE public.dataset_catalog
    SET active_version_id = v_version_id, updated_at = now()
    WHERE id = v_catalog_id;

    RETURN QUERY
    SELECT version.*
    FROM public.dataset_versions version
    WHERE version.id = v_version_id;
END;
$$;

REVOKE ALL ON FUNCTION public.register_dataset_version(
    UUID, TEXT, TEXT, JSONB, TEXT, TEXT, TEXT, TEXT,
    UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_dataset_version(
    UUID, TEXT, TEXT, JSONB, TEXT, TEXT, TEXT, TEXT,
    UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB
) TO service_role;

DO $$
DECLARE
    session_row RECORD;
    canonical_key TEXT;
BEGIN
    FOR session_row IN
        SELECT
            setup.*,
            run.output_version
        FROM public.data_setup_sessions setup
        LEFT JOIN public.etl_pipeline_runs run ON run.id = setup.run_id
        WHERE setup.status = 'ready'
          AND setup.output_dataset_key IS NOT NULL
          AND setup.output_file IS NOT NULL
          AND setup.dataset_version_id IS NULL
    LOOP
        canonical_key := session_row.source_type || ':' || CASE
            WHEN session_row.source_type = 'file'
                THEN COALESCE(session_row.source_ref->>'file_name', session_row.id::text)
            WHEN session_row.source_type = 'sql'
                THEN COALESCE(session_row.source_ref->>'connection_id', session_row.id::text)
                    || ':' || COALESCE(session_row.source_ref->>'table_name', '')
            ELSE COALESCE(session_row.source_ref->>'connection_id', session_row.id::text)
        END;

        PERFORM public.register_dataset_version(
            session_row.user_id,
            canonical_key,
            session_row.source_type,
            session_row.source_ref,
            COALESCE(session_row.scan_result->>'source_label', session_row.output_dataset_key),
            session_row.source_fingerprint,
            session_row.recipe_hash,
            session_row.contract_hash,
            session_row.recipe_id,
            session_row.run_id,
            session_row.id,
            session_row.output_dataset_key,
            session_row.output_file,
            session_row.output_version,
            jsonb_build_object(
                'trigger_kind', 'data_setup_backfill',
                'source_ref', session_row.source_ref,
                'materialized_prepared', TRUE
            )
        );

        UPDATE public.data_setup_sessions setup
        SET dataset_version_id = version.id
        FROM public.dataset_versions version
        WHERE setup.id = session_row.id
          AND version.data_setup_session_id = session_row.id;
    END LOOP;
END;
$$;

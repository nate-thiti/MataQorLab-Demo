-- Dataset-scoped semantic mapping memory and governed column context.
-- Safe to apply after column_mappings_memory.sql and etl_workflows.sql.

CREATE TABLE IF NOT EXISTS public.dataset_mapping_memory (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL CHECK (btrim(dataset_key) <> ''),
    original_column TEXT NOT NULL CHECK (btrim(original_column) <> ''),
    mapped_semantic TEXT NOT NULL CHECK (btrim(mapped_semantic) <> ''),
    column_contract JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(column_contract) = 'object'),
    mapping_source TEXT NOT NULL DEFAULT 'user'
        CHECK (mapping_source IN ('user', 'suggested', 'imported')),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, dataset_key, original_column)
);

CREATE INDEX IF NOT EXISTS idx_dataset_mapping_memory_user_dataset
    ON public.dataset_mapping_memory (user_id, dataset_key);

ALTER TABLE public.dataset_mapping_memory ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own dataset mapping memory"
    ON public.dataset_mapping_memory;
CREATE POLICY "Users read own dataset mapping memory"
    ON public.dataset_mapping_memory
    FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users insert own dataset mapping memory"
    ON public.dataset_mapping_memory;
CREATE POLICY "Users insert own dataset mapping memory"
    ON public.dataset_mapping_memory
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users update own dataset mapping memory"
    ON public.dataset_mapping_memory;
CREATE POLICY "Users update own dataset mapping memory"
    ON public.dataset_mapping_memory
    FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users delete own dataset mapping memory"
    ON public.dataset_mapping_memory;
CREATE POLICY "Users delete own dataset mapping memory"
    ON public.dataset_mapping_memory
    FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

REVOKE ALL ON public.dataset_mapping_memory FROM anon, PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.dataset_mapping_memory TO authenticated;
GRANT ALL ON public.dataset_mapping_memory TO service_role;

COMMENT ON TABLE public.dataset_mapping_memory IS
    'User-owned semantic mappings scoped to one dataset, with column-level business and governance metadata';

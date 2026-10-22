-- Run in Supabase SQL editor (Dashboard → SQL → New query)
-- Safe to re-run: uses IF NOT EXISTS / DROP POLICY IF EXISTS.
-- Stores per-user column mapping memory for the mapping modal (Layer 12).

CREATE TABLE IF NOT EXISTS public.column_mappings_memory (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    original_column TEXT NOT NULL,
    mapped_semantic TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, original_column)
);

CREATE INDEX IF NOT EXISTS idx_column_mappings_memory_user
    ON public.column_mappings_memory (user_id);

ALTER TABLE public.column_mappings_memory ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users read own column mappings"
    ON public.column_mappings_memory
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users insert own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users insert own column mappings"
    ON public.column_mappings_memory
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users update own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users update own column mappings"
    ON public.column_mappings_memory
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users delete own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users delete own column mappings"
    ON public.column_mappings_memory
    FOR DELETE
    USING (auth.uid() = user_id);

COMMENT ON TABLE public.column_mappings_memory IS 'User column → semantic role mapping memory for chat file uploads';
COMMENT ON COLUMN public.column_mappings_memory.user_id IS 'Same as profiles.id / auth.users.id';

-- If the table already exists without FK, run once in SQL editor:
-- ALTER TABLE public.column_mappings_memory
--   ADD CONSTRAINT column_mappings_memory_user_id_fkey
--   FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

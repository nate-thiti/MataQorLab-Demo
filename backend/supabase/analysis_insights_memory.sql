-- Per-user dataset insight memory for RAG-style context in chat.
-- Run in Supabase Dashboard → SQL Editor.

CREATE TABLE IF NOT EXISTS public.analysis_insights_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL,
    question TEXT NOT NULL,
    insight TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analysis_insights_memory_user_dataset
    ON public.analysis_insights_memory (user_id, dataset_key, created_at DESC);

ALTER TABLE public.analysis_insights_memory ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users read own analysis insights"
    ON public.analysis_insights_memory
    FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users insert own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users insert own analysis insights"
    ON public.analysis_insights_memory
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users delete own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users delete own analysis insights"
    ON public.analysis_insights_memory
    FOR DELETE
    USING (auth.uid() = user_id);

COMMENT ON TABLE public.analysis_insights_memory IS
    'Prior Q&A insights per user+dataset for lightweight RAG in chat context';

-- Existing deployments: remove orphan rows, then add FK if missing (safe to re-run)
DELETE FROM public.analysis_insights_memory aim
WHERE NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = aim.user_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.analysis_insights_memory'::regclass
          AND conname = 'analysis_insights_memory_user_id_fkey'
    ) THEN
        ALTER TABLE public.analysis_insights_memory
            ADD CONSTRAINT analysis_insights_memory_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

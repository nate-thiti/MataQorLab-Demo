-- Persistent, resumable state for the adaptive first-use data setup flow.

CREATE TABLE IF NOT EXISTS public.data_setup_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('file', 'api', 'sql')),
    source_ref JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(source_ref) = 'object'),
    source_fingerprint TEXT,
    status TEXT NOT NULL DEFAULT 'scanning'
        CHECK (status IN (
            'scanning', 'awaiting_answers', 'previewing', 'preview_ready',
            'approved', 'processing', 'ready', 'failed', 'cancelled'
        )),
    current_step TEXT NOT NULL DEFAULT 'scan'
        CHECK (current_step IN (
            'scan', 'structure', 'mapping', 'cleaning', 'business_context',
            'review', 'processing', 'ready'
        )),
    original_prompt TEXT NOT NULL DEFAULT '' CHECK (char_length(original_prompt) <= 4000),
    scan_result JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(scan_result) = 'object'),
    answers JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(answers) = 'object'),
    column_mapping JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(column_mapping) = 'object'),
    cleaning_profile TEXT NOT NULL DEFAULT 'standard'
        CHECK (cleaning_profile IN ('standard', 'financial', 'conservative', 'aggressive')),
    cleaning_recipe JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(cleaning_recipe) = 'object'),
    business_context JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(business_context) = 'object'),
    preview_result JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(preview_result) = 'object'),
    processing_progress JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(processing_progress) = 'object'),
    recipe_id UUID REFERENCES public.etl_recipes(id) ON DELETE SET NULL,
    run_id UUID REFERENCES public.etl_pipeline_runs(id) ON DELETE SET NULL,
    output_dataset_key TEXT,
    output_file TEXT,
    error_message TEXT CHECK (error_message IS NULL OR char_length(error_message) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_user_updated
    ON public.data_setup_sessions (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_conversation
    ON public.data_setup_sessions (conversation_id)
    WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_recipe
    ON public.data_setup_sessions (recipe_id)
    WHERE recipe_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_run
    ON public.data_setup_sessions (run_id)
    WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_data_setup_sessions_active
    ON public.data_setup_sessions (user_id, status, updated_at DESC)
    WHERE status NOT IN ('ready', 'failed', 'cancelled');

ALTER TABLE public.data_setup_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own data setup sessions" ON public.data_setup_sessions;
CREATE POLICY "Users read own data setup sessions"
    ON public.data_setup_sessions FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

REVOKE ALL ON public.data_setup_sessions FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.data_setup_sessions TO authenticated;
GRANT ALL ON public.data_setup_sessions TO service_role;

CREATE OR REPLACE FUNCTION public.claim_data_setup_session(p_session_id UUID)
RETURNS SETOF public.data_setup_sessions
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.data_setup_sessions AS session
       SET status = 'processing',
           current_step = 'processing',
           processing_progress = '{"percent":5,"stage":"claimed"}'::jsonb,
           updated_at = now()
     WHERE session.id = p_session_id
       AND session.status = 'approved'
    RETURNING session.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_data_setup_sessions(p_limit INTEGER DEFAULT 2)
RETURNS SETOF public.data_setup_sessions
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    WITH candidates AS (
        SELECT session.id
          FROM public.data_setup_sessions AS session
         WHERE session.status = 'approved'
            OR (
                session.status = 'processing'
                AND session.updated_at < now() - interval '2 hours'
            )
         ORDER BY session.updated_at
         FOR UPDATE SKIP LOCKED
         LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 2), 10))
    )
    UPDATE public.data_setup_sessions AS session
       SET status = 'processing',
           current_step = 'processing',
           processing_progress = '{"percent":5,"stage":"claimed"}'::jsonb,
           updated_at = now()
      FROM candidates
     WHERE session.id = candidates.id
    RETURNING session.*;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_data_setup_session(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_data_setup_sessions(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_data_setup_session(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_data_setup_sessions(INTEGER) TO service_role;

COMMENT ON TABLE public.data_setup_sessions IS
    'Owner-scoped state and audit trail for adaptive Source → Contract → ETL onboarding.';
COMMENT ON COLUMN public.data_setup_sessions.scan_result IS
    'Bounded schema/profile metadata only; raw sample rows are not persisted.';

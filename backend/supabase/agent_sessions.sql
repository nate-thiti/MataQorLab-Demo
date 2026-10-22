-- Run in Supabase SQL editor when using AGENT_SESSION_BACKEND=supabase
-- Safe to re-run: uses IF NOT EXISTS / DROP POLICY IF EXISTS.
-- Enables multi-instance agent pause/resume across backend replicas.

CREATE TABLE IF NOT EXISTS public.agent_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    session_data JSONB NOT NULL,
    parquet_path TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Optional: enable RLS and policies if exposing to client (backend uses service role)
ALTER TABLE public.agent_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access agent_sessions" ON public.agent_sessions;
CREATE POLICY "Service role full access agent_sessions"
    ON public.agent_sessions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL ON TABLE public.agent_sessions FROM anon, authenticated;

COMMENT ON TABLE public.agent_sessions IS 'Autonomous analysis agent pause/resume sessions';

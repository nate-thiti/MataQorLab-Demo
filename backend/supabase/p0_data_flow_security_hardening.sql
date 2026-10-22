-- P0 hardening for encrypted connectors, immutable ETL audit and idempotent Data Setup.
-- Configure CONNECTION_SECRET_KEY on every backend/worker before deploying the
-- backend code. Run backend/scripts/reencrypt_connection_secrets.py once after apply.

ALTER TABLE public.api_connections
    ADD COLUMN IF NOT EXISTS secrets_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS secret_version INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.api_connections.secrets_encrypted IS
    'AES-256-GCM application ciphertext; decrypted only by trusted backend workers.';

ALTER TABLE public.data_setup_sessions
    ADD COLUMN IF NOT EXISTS recipe_hash TEXT,
    ADD COLUMN IF NOT EXISTS contract_hash TEXT;

ALTER TABLE public.etl_pipeline_runs
    DROP CONSTRAINT IF EXISTS etl_pipeline_runs_trigger_kind_check;
ALTER TABLE public.etl_pipeline_runs
    ADD CONSTRAINT etl_pipeline_runs_trigger_kind_check
    CHECK (trigger_kind IN ('manual', 'cron', 'on_upload', 'data_setup'));

DROP INDEX IF EXISTS public.idx_data_setup_sessions_one_active_source;
CREATE UNIQUE INDEX idx_data_setup_sessions_one_active_source
    ON public.data_setup_sessions (user_id, source_fingerprint)
    WHERE source_fingerprint IS NOT NULL
      AND status IN (
          'scanning', 'awaiting_answers', 'previewing', 'preview_ready',
          'approved', 'processing'
      );

-- Connector rows are backend-only. RLS remains enabled as defense in depth,
-- but browser roles no longer have table-level access to ciphertext or metadata.
REVOKE ALL ON TABLE public.api_connections FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.database_connections FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.api_connections TO service_role;
GRANT ALL ON TABLE public.database_connections TO service_role;

-- Pipeline runs are an immutable audit stream for customer roles.
DROP POLICY IF EXISTS "Users insert own etl_pipeline_runs" ON public.etl_pipeline_runs;
DROP POLICY IF EXISTS "Users update own etl_pipeline_runs" ON public.etl_pipeline_runs;
DROP POLICY IF EXISTS "Users delete own etl_pipeline_runs" ON public.etl_pipeline_runs;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.etl_pipeline_runs FROM authenticated;
GRANT SELECT ON public.etl_pipeline_runs TO authenticated;

-- Quality alerts are backend-created. Customers may only acknowledge their own
-- rows, and the column grant prevents editing severity/rule/evidence.
DROP POLICY IF EXISTS "Users insert own etl_quality_alerts" ON public.etl_quality_alerts;
DROP POLICY IF EXISTS "Users delete own etl_quality_alerts" ON public.etl_quality_alerts;
REVOKE INSERT, DELETE, TRUNCATE ON public.etl_quality_alerts FROM authenticated;
REVOKE UPDATE ON public.etl_quality_alerts FROM authenticated;
GRANT SELECT ON public.etl_quality_alerts TO authenticated;
GRANT UPDATE (acknowledged_at) ON public.etl_quality_alerts TO authenticated;

GRANT ALL ON TABLE public.etl_pipeline_runs TO service_role;
GRANT ALL ON TABLE public.etl_quality_alerts TO service_role;

-- Supabase publishable/secret API keys are opaque and do not populate the
-- legacy request.jwt.claim.role setting. Authorization is enforced by the
-- EXECUTE grants below and the invoker's table privileges.
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

REVOKE ALL ON FUNCTION public.claim_data_setup_session(UUID)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_data_setup_sessions(INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_data_setup_session(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_data_setup_sessions(INTEGER) TO service_role;


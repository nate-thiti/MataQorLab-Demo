-- Phase 3: per-step workflow persistence for adaptive Data Setup.
-- Apply after adaptive_data_setup_copilot.sql (and later data_setup hardenings).

-- Lightweight session summary fields (cache only; workflow_steps is source of truth).
ALTER TABLE public.data_setup_sessions
    ADD COLUMN IF NOT EXISTS next_action TEXT
        CHECK (next_action IS NULL OR char_length(next_action) <= 100),
    ADD COLUMN IF NOT EXISTS last_failed_step TEXT
        CHECK (last_failed_step IS NULL OR char_length(last_failed_step) <= 40);

CREATE TABLE IF NOT EXISTS public.workflow_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_setup_session_id UUID NOT NULL
        REFERENCES public.data_setup_sessions(id) ON DELETE CASCADE,
    step_type TEXT NOT NULL
        CHECK (step_type IN (
            'inspect', 'prepare', 'map', 'validate', 'clean', 'finalize'
        )),
    status TEXT NOT NULL
        CHECK (status IN (
            'pending', 'ready', 'running', 'awaiting_user',
            'completed', 'failed', 'skipped', 'stale', 'superseded'
        )),
    -- Version = logical result generation (input/config change).
    -- Attempt = retry of the same logical version after failure.
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    attempt INTEGER NOT NULL DEFAULT 1
        CHECK (attempt >= 1),
    input JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(input) = 'object'),
    output JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(output) = 'object'),
    reason TEXT
        CHECK (reason IS NULL OR char_length(reason) <= 2000),
    error_code TEXT
        CHECK (error_code IS NULL OR char_length(error_code) <= 100),
    error_message TEXT
        CHECK (error_message IS NULL OR char_length(error_message) <= 2000),
    requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.workflow_steps IS
    'Per-tool execution history for data_setup_sessions. Attempt retries same version; version bumps when inputs change.';
COMMENT ON COLUMN public.workflow_steps.version IS
    'Logical result generation; bump when configuration/input materially changes.';
COMMENT ON COLUMN public.workflow_steps.attempt IS
    'Retry count within the same version after failure.';

-- One row per (session, step, version, attempt) for auditable history.
CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_steps_session_type_version_attempt
    ON public.workflow_steps (data_setup_session_id, step_type, version, attempt);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_session_updated
    ON public.workflow_steps (data_setup_session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_session_status
    ON public.workflow_steps (data_setup_session_id, status);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_session_type
    ON public.workflow_steps (data_setup_session_id, step_type);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_status
    ON public.workflow_steps (status)
    WHERE status IN ('running', 'failed', 'awaiting_user');

ALTER TABLE public.workflow_steps ENABLE ROW LEVEL SECURITY;

-- Customers may read steps only for sessions they own. Writes are backend-only.
DROP POLICY IF EXISTS "Users read own workflow steps" ON public.workflow_steps;
CREATE POLICY "Users read own workflow steps"
    ON public.workflow_steps FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1
              FROM public.data_setup_sessions AS session
             WHERE session.id = workflow_steps.data_setup_session_id
               AND session.user_id = (SELECT auth.uid())
        )
    );

REVOKE ALL ON public.workflow_steps FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.workflow_steps TO authenticated;
GRANT ALL ON public.workflow_steps TO service_role;

-- Atomically begin or reclaim a step for the owning session.
-- Returns the completed/skipped/running row the caller should honor.
CREATE OR REPLACE FUNCTION public.begin_workflow_step(
    p_session_id UUID,
    p_step_type TEXT,
    p_input JSONB DEFAULT '{}'::jsonb,
    p_bump_version BOOLEAN DEFAULT FALSE
)
RETURNS SETOF public.workflow_steps
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    latest public.workflow_steps%ROWTYPE;
    next_version INTEGER;
    next_attempt INTEGER;
BEGIN
    IF p_step_type IS NULL OR p_step_type NOT IN (
        'inspect', 'prepare', 'map', 'validate', 'clean', 'finalize'
    ) THEN
        RAISE EXCEPTION 'invalid_step_type';
    END IF;

    -- Serialize step mutations per session.
    PERFORM 1
      FROM public.data_setup_sessions AS session
     WHERE session.id = p_session_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT step.*
      INTO latest
      FROM public.workflow_steps AS step
     WHERE step.data_setup_session_id = p_session_id
       AND step.step_type = p_step_type
     ORDER BY step.version DESC, step.attempt DESC
     LIMIT 1;

    IF FOUND THEN
        IF latest.status IN ('completed', 'skipped') AND NOT p_bump_version THEN
            RETURN NEXT latest;
            RETURN;
        END IF;

        IF latest.status = 'running'
           AND latest.updated_at > now() - interval '2 hours'
           AND NOT p_bump_version THEN
            RETURN NEXT latest;
            RETURN;
        END IF;

        IF p_bump_version THEN
            next_version := latest.version + 1;
            next_attempt := 1;
            UPDATE public.workflow_steps AS step
               SET status = 'superseded',
                   updated_at = now()
             WHERE step.data_setup_session_id = p_session_id
               AND step.step_type = p_step_type
               AND step.status NOT IN ('superseded', 'stale');
        ELSE
            next_version := latest.version;
            next_attempt := CASE
                WHEN latest.status IN ('failed', 'stale', 'running')
                    THEN latest.attempt + 1
                ELSE latest.attempt
            END;
            IF latest.status = 'running' THEN
                UPDATE public.workflow_steps AS step
                   SET status = 'failed',
                       error_code = 'STEP_CLAIM_TIMEOUT',
                       error_message = 'Previous running attempt was reclaimed',
                       completed_at = now(),
                       updated_at = now()
                 WHERE step.id = latest.id;
            END IF;
        END IF;
    ELSE
        next_version := 1;
        next_attempt := 1;
    END IF;

    RETURN QUERY
    INSERT INTO public.workflow_steps AS step (
        data_setup_session_id,
        step_type,
        status,
        version,
        attempt,
        input,
        started_at,
        updated_at
    ) VALUES (
        p_session_id,
        p_step_type,
        'running',
        next_version,
        next_attempt,
        COALESCE(p_input, '{}'::jsonb),
        now(),
        now()
    )
    RETURNING step.*;
END;
$$;

REVOKE ALL ON FUNCTION public.begin_workflow_step(UUID, TEXT, JSONB, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.begin_workflow_step(UUID, TEXT, JSONB, BOOLEAN)
    TO service_role;

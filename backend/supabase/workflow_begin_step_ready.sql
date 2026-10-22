-- Phase 4.5: begin_workflow_step must reclaim approved (ready) rows in place
-- so confirmation fingerprints remain bound to the executing attempt.

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

        -- Approved confirmation: reclaim same row (preserve confirmation audit).
        IF latest.status = 'ready' AND NOT p_bump_version THEN
            UPDATE public.workflow_steps AS step
               SET status = 'running',
                   input = COALESCE(p_input, '{}'::jsonb) || COALESCE(step.input, '{}'::jsonb),
                   requires_confirmation = FALSE,
                   started_at = COALESCE(step.started_at, now()),
                   updated_at = now()
             WHERE step.id = latest.id
         RETURNING step.* INTO latest;
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
                WHEN latest.status IN ('failed', 'stale', 'running', 'awaiting_user')
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
            ELSIF latest.status = 'awaiting_user' THEN
                UPDATE public.workflow_steps AS step
                   SET status = 'superseded',
                       reason = COALESCE(step.reason, 'superseded by new attempt'),
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

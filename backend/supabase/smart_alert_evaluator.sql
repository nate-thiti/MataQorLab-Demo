-- Lease-based Smart Alert evaluation state and delivery evidence.
-- Apply after customer_experience_platform.sql.

ALTER TABLE public.customer_alert_rules
    ADD COLUMN IF NOT EXISTS filter_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS evaluation_interval_minutes INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS next_evaluation_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_value NUMERIC,
    ADD COLUMN IF NOT EXISTS last_status TEXT NOT NULL DEFAULT 'idle',
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS locked_by TEXT;

ALTER TABLE public.customer_alert_events
    ADD COLUMN IF NOT EXISTS evaluation_key TEXT,
    ADD COLUMN IF NOT EXISTS comparison_value NUMERIC,
    ADD COLUMN IF NOT EXISTS delivery_results JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_rules_filter_state_object'
          AND conrelid = 'public.customer_alert_rules'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_rules
            ADD CONSTRAINT customer_alert_rules_filter_state_object
            CHECK (jsonb_typeof(filter_state) = 'object');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_rules_evaluation_interval_range'
          AND conrelid = 'public.customer_alert_rules'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_rules
            ADD CONSTRAINT customer_alert_rules_evaluation_interval_range
            CHECK (evaluation_interval_minutes BETWEEN 1 AND 1440);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_rules_last_status_valid'
          AND conrelid = 'public.customer_alert_rules'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_rules
            ADD CONSTRAINT customer_alert_rules_last_status_valid
            CHECK (last_status IN (
                'idle', 'running', 'baseline', 'not_triggered',
                'suppressed', 'delivered', 'failed'
            ));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_rules_failures_nonnegative'
          AND conrelid = 'public.customer_alert_rules'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_rules
            ADD CONSTRAINT customer_alert_rules_failures_nonnegative
            CHECK (consecutive_failures >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_rules_last_error_length'
          AND conrelid = 'public.customer_alert_rules'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_rules
            ADD CONSTRAINT customer_alert_rules_last_error_length
            CHECK (last_error IS NULL OR char_length(last_error) <= 2000);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_events_evaluation_key_length'
          AND conrelid = 'public.customer_alert_events'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_events
            ADD CONSTRAINT customer_alert_events_evaluation_key_length
            CHECK (evaluation_key IS NULL OR char_length(evaluation_key) = 64);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_alert_events_delivery_results_object'
          AND conrelid = 'public.customer_alert_events'::regclass
    ) THEN
        ALTER TABLE public.customer_alert_events
            ADD CONSTRAINT customer_alert_events_delivery_results_object
            CHECK (jsonb_typeof(delivery_results) = 'object');
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_alert_events_evaluation_key
    ON public.customer_alert_events (evaluation_key)
    WHERE evaluation_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customer_alert_rules_due
    ON public.customer_alert_rules (next_evaluation_at, id)
    WHERE enabled = TRUE;

CREATE OR REPLACE FUNCTION public.claim_due_customer_alert_rules(
    p_worker_id TEXT,
    p_limit INTEGER DEFAULT 5,
    p_lease_seconds INTEGER DEFAULT 300
)
RETURNS SETOF public.customer_alert_rules
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.customer_alert_rules AS rule
    SET locked_at = now(),
        locked_by = left(p_worker_id, 200),
        last_status = 'running',
        last_error = NULL,
        updated_at = now()
    WHERE rule.id IN (
        SELECT candidate.id
        FROM public.customer_alert_rules AS candidate
        WHERE candidate.enabled = TRUE
          AND candidate.report_id IS NOT NULL
          AND candidate.next_evaluation_at <= now()
          AND (
              candidate.locked_at IS NULL
              OR candidate.locked_at < now() - make_interval(
                  secs => greatest(30, least(p_lease_seconds, 3600))
              )
          )
        ORDER BY candidate.next_evaluation_at, candidate.id
        FOR UPDATE SKIP LOCKED
        LIMIT greatest(1, least(p_limit, 50))
    )
    RETURNING rule.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_customer_alert_rule(
    p_rule_id UUID,
    p_user_id UUID,
    p_worker_id TEXT,
    p_lease_seconds INTEGER DEFAULT 300
)
RETURNS SETOF public.customer_alert_rules
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.customer_alert_rules AS rule
    SET locked_at = now(),
        locked_by = left(p_worker_id, 200),
        last_status = 'running',
        last_error = NULL,
        updated_at = now()
    WHERE rule.id = p_rule_id
      AND rule.user_id = p_user_id
      AND rule.enabled = TRUE
      AND rule.report_id IS NOT NULL
      AND (
          rule.locked_at IS NULL
          OR rule.locked_at < now() - make_interval(
              secs => greatest(30, least(p_lease_seconds, 3600))
          )
      )
    RETURNING rule.*;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_due_customer_alert_rules(TEXT, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_customer_alert_rule(UUID, UUID, TEXT, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_due_customer_alert_rules(TEXT, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_customer_alert_rule(UUID, UUID, TEXT, INTEGER)
    TO service_role;

COMMENT ON FUNCTION public.claim_due_customer_alert_rules(TEXT, INTEGER, INTEGER) IS
    'Atomically leases due Smart Alert rules for backend workers';

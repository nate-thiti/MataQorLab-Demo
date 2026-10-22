-- Versioned, user-owned ETL recipes, runs, schedules, and data-quality alerts.
-- Apply once in Supabase SQL Editor. Safe to re-run.

CREATE TABLE IF NOT EXISTS public.etl_recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    recipe JSONB NOT NULL CHECK (jsonb_typeof(recipe) = 'object'),
    recipe_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, dataset_key, version)
);

CREATE INDEX IF NOT EXISTS idx_etl_recipes_user_dataset
    ON public.etl_recipes (user_id, dataset_key, version DESC);

CREATE TABLE IF NOT EXISTS public.etl_pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    recipe_id UUID REFERENCES public.etl_recipes(id) ON DELETE SET NULL,
    trigger_kind TEXT NOT NULL DEFAULT 'manual'
        CHECK (trigger_kind IN ('manual', 'cron', 'on_upload', 'data_setup')),
    dataset_key TEXT NOT NULL,
    output_dataset_key TEXT,
    status TEXT NOT NULL CHECK (status IN ('previewed', 'queued', 'running', 'completed', 'failed', 'rolled_back')),
    recipe_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(recipe_snapshot) = 'object'),
    input_rows BIGINT,
    output_rows BIGINT,
    input_version TEXT,
    output_version TEXT,
    report JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(report) = 'object'),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_etl_pipeline_runs_user_dataset
    ON public.etl_pipeline_runs (user_id, dataset_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_pipeline_runs_recipe
    ON public.etl_pipeline_runs (recipe_id);

CREATE TABLE IF NOT EXISTS public.etl_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    recipe_id UUID NOT NULL REFERENCES public.etl_recipes(id) ON DELETE CASCADE,
    schedule_kind TEXT NOT NULL DEFAULT 'manual'
        CHECK (schedule_kind IN ('manual', 'cron', 'on_upload')),
    cron_expression TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    output_name TEXT,
    output_dataset_key TEXT NOT NULL,
    latest_output_file TEXT,
    latest_output_version TEXT,
    incremental_column TEXT,
    last_cursor JSONB,
    alert_config JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(alert_config) = 'object'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_run_id UUID REFERENCES public.etl_pipeline_runs(id) ON DELETE SET NULL,
    last_status TEXT,
    last_error TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, recipe_id)
);

ALTER TABLE public.etl_pipeline_runs
    ADD COLUMN IF NOT EXISTS trigger_kind TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE public.etl_pipeline_runs
    ADD COLUMN IF NOT EXISTS schedule_id UUID;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS output_name TEXT;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS output_dataset_key TEXT;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS latest_output_file TEXT;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS latest_output_version TEXT;
UPDATE public.etl_schedules
SET output_dataset_key = 'etl:' || id::text
WHERE output_dataset_key IS NULL OR btrim(output_dataset_key) = '';
ALTER TABLE public.etl_schedules
    ALTER COLUMN output_dataset_key SET NOT NULL;
ALTER TABLE public.etl_pipeline_runs
    ADD COLUMN IF NOT EXISTS output_dataset_key TEXT;
UPDATE public.etl_pipeline_runs AS run
SET output_dataset_key = schedule.output_dataset_key
FROM public.etl_schedules AS schedule
WHERE run.schedule_id = schedule.id
  AND run.output_dataset_key IS NULL;
UPDATE public.etl_schedules AS schedule
SET latest_output_file = latest.output_version,
    latest_output_version = latest.output_version
FROM (
    SELECT DISTINCT ON (schedule_id)
        schedule_id,
        output_version
    FROM public.etl_pipeline_runs
    WHERE schedule_id IS NOT NULL
      AND status = 'completed'
      AND output_version IS NOT NULL
    ORDER BY schedule_id, completed_at DESC NULLS LAST, created_at DESC
) AS latest
WHERE latest.schedule_id = schedule.id
  AND schedule.latest_output_file IS NULL;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS last_status TEXT;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS last_run_id UUID;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS locked_by TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_pipeline_runs_schedule_id_fkey'
          AND conrelid = 'public.etl_pipeline_runs'::regclass
    ) THEN
        ALTER TABLE public.etl_pipeline_runs
            ADD CONSTRAINT etl_pipeline_runs_schedule_id_fkey
            FOREIGN KEY (schedule_id)
            REFERENCES public.etl_schedules(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_schedules_last_run_id_fkey'
          AND conrelid = 'public.etl_schedules'::regclass
    ) THEN
        ALTER TABLE public.etl_schedules
            ADD CONSTRAINT etl_schedules_last_run_id_fkey
            FOREIGN KEY (last_run_id)
            REFERENCES public.etl_pipeline_runs(id)
            ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_pipeline_runs_trigger_kind_check'
          AND conrelid = 'public.etl_pipeline_runs'::regclass
    ) THEN
        ALTER TABLE public.etl_pipeline_runs
            ADD CONSTRAINT etl_pipeline_runs_trigger_kind_check
            CHECK (trigger_kind IN ('manual', 'cron', 'on_upload', 'data_setup'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_schedules_consecutive_failures_check'
          AND conrelid = 'public.etl_schedules'::regclass
    ) THEN
        ALTER TABLE public.etl_schedules
            ADD CONSTRAINT etl_schedules_consecutive_failures_check
            CHECK (consecutive_failures >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'etl_schedules_last_status_check'
          AND conrelid = 'public.etl_schedules'::regclass
    ) THEN
        ALTER TABLE public.etl_schedules
            ADD CONSTRAINT etl_schedules_last_status_check
            CHECK (
                last_status IS NULL
                OR last_status IN ('scheduled', 'running', 'completed', 'failed', 'paused')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_etl_schedules_due
    ON public.etl_schedules (next_run_at)
    WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_etl_schedules_user
    ON public.etl_schedules (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_schedules_recipe
    ON public.etl_schedules (recipe_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_etl_schedules_output_dataset
    ON public.etl_schedules (user_id, output_dataset_key);
CREATE INDEX IF NOT EXISTS idx_etl_pipeline_runs_output_dataset
    ON public.etl_pipeline_runs (user_id, output_dataset_key, created_at DESC)
    WHERE output_dataset_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_etl_pipeline_runs_schedule
    ON public.etl_pipeline_runs (schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_schedules_last_run
    ON public.etl_schedules (last_run_id)
    WHERE last_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.etl_quality_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES public.etl_pipeline_runs(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning'
        CHECK (severity IN ('info', 'warning', 'critical')),
    rule_key TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detail) = 'object'),
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_etl_quality_alerts_user
    ON public.etl_quality_alerts (user_id, acknowledged_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_etl_quality_alerts_run
    ON public.etl_quality_alerts (run_id);

ALTER TABLE public.etl_recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etl_pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etl_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etl_quality_alerts ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'etl_recipes', 'etl_pipeline_runs', 'etl_schedules', 'etl_quality_alerts'
    ]
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS "Users read own %1$s" ON public.%1$I', table_name);
        EXECUTE format(
            'CREATE POLICY "Users read own %1$s" ON public.%1$I FOR SELECT TO authenticated USING ((SELECT auth.uid()) = user_id)',
            table_name
        );
        EXECUTE format('DROP POLICY IF EXISTS "Users insert own %1$s" ON public.%1$I', table_name);
        EXECUTE format(
            'CREATE POLICY "Users insert own %1$s" ON public.%1$I FOR INSERT TO authenticated WITH CHECK ((SELECT auth.uid()) = user_id)',
            table_name
        );
        EXECUTE format('DROP POLICY IF EXISTS "Users update own %1$s" ON public.%1$I', table_name);
        EXECUTE format(
            'CREATE POLICY "Users update own %1$s" ON public.%1$I FOR UPDATE TO authenticated USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id)',
            table_name
        );
        EXECUTE format('DROP POLICY IF EXISTS "Users delete own %1$s" ON public.%1$I', table_name);
        EXECUTE format(
            'CREATE POLICY "Users delete own %1$s" ON public.%1$I FOR DELETE TO authenticated USING ((SELECT auth.uid()) = user_id)',
            table_name
        );
    END LOOP;
END $$;

REVOKE ALL ON
    public.etl_recipes,
    public.etl_pipeline_runs,
    public.etl_schedules,
    public.etl_quality_alerts
FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.etl_recipes,
    public.etl_pipeline_runs,
    public.etl_schedules,
    public.etl_quality_alerts
TO authenticated;

GRANT ALL ON
    public.etl_recipes,
    public.etl_pipeline_runs,
    public.etl_schedules,
    public.etl_quality_alerts
TO service_role;

-- Atomically lease due jobs so multiple backend replicas cannot run one schedule twice.
CREATE OR REPLACE FUNCTION public.claim_due_etl_schedules(
    p_worker_id TEXT,
    p_limit INTEGER DEFAULT 3,
    p_lease_seconds INTEGER DEFAULT 900
)
RETURNS SETOF public.etl_schedules
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.etl_schedules AS schedule
    SET locked_at = now(),
        locked_by = left(p_worker_id, 200),
        last_status = 'running',
        last_error = NULL,
        updated_at = now()
    WHERE schedule.id IN (
        SELECT candidate.id
        FROM public.etl_schedules AS candidate
        WHERE candidate.enabled = TRUE
          AND candidate.schedule_kind = 'cron'
          AND candidate.next_run_at IS NOT NULL
          AND candidate.next_run_at <= now()
          AND (
              candidate.locked_at IS NULL
              OR candidate.locked_at < now() - make_interval(
                  secs => greatest(60, least(p_lease_seconds, 86400))
              )
          )
        ORDER BY candidate.next_run_at, candidate.id
        FOR UPDATE SKIP LOCKED
        LIMIT greatest(1, least(p_limit, 20))
    )
    RETURNING schedule.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_etl_schedule(
    p_schedule_id UUID,
    p_worker_id TEXT,
    p_lease_seconds INTEGER DEFAULT 900
)
RETURNS SETOF public.etl_schedules
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.etl_schedules AS schedule
    SET locked_at = now(),
        locked_by = left(p_worker_id, 200),
        last_status = 'running',
        last_error = NULL,
        updated_at = now()
    WHERE schedule.id = p_schedule_id
      AND (
          schedule.locked_at IS NULL
          OR schedule.locked_at < now() - make_interval(
              secs => greatest(60, least(p_lease_seconds, 86400))
          )
      )
    RETURNING schedule.*;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_due_etl_schedules(TEXT, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_etl_schedule(UUID, TEXT, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_due_etl_schedules(TEXT, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_etl_schedule(UUID, TEXT, INTEGER)
    TO service_role;

REVOKE ALL ON
    public.etl_recipes,
    public.etl_pipeline_runs,
    public.etl_schedules,
    public.etl_quality_alerts
FROM anon;

COMMENT ON TABLE public.etl_recipes IS
    'Versioned deterministic ETL recipes approved by each dataset owner';
COMMENT ON TABLE public.etl_pipeline_runs IS
    'Immutable-style execution and preview audit records; no raw customer rows';
COMMENT ON TABLE public.etl_schedules IS
    'Cron/on-upload scheduling metadata with one stable output dataset identity per schedule';
COMMENT ON TABLE public.etl_quality_alerts IS
    'User-owned data-quality alerts emitted from ETL runs';

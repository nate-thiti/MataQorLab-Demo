-- Delivery-candidate telemetry for scheduled ETL automation.
-- Scheduled ETL does not send messages; eligible/suppressed decisions are audited here.

CREATE TABLE IF NOT EXISTS public.automation_delivery_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    schedule_id UUID NOT NULL REFERENCES public.etl_schedules(id) ON DELETE CASCADE,
    run_id UUID REFERENCES public.etl_pipeline_runs(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('previewed', 'eligible', 'suppressed', 'delivered', 'opened', 'muted')),
    severity TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('info', 'warning', 'critical')),
    fingerprint TEXT,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(reason_codes) = 'array'),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metrics) = 'object'),
    opened_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automation_delivery_events_user
    ON public.automation_delivery_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_delivery_events_schedule
    ON public.automation_delivery_events (schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_delivery_events_run
    ON public.automation_delivery_events (run_id)
    WHERE run_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_delivery_events_dedup
    ON public.automation_delivery_events (schedule_id, fingerprint, event_type)
    WHERE fingerprint IS NOT NULL;

ALTER TABLE public.automation_delivery_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own automation_delivery_events"
    ON public.automation_delivery_events;
CREATE POLICY "Users read own automation_delivery_events"
    ON public.automation_delivery_events FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users update own automation_delivery_events"
    ON public.automation_delivery_events;
CREATE POLICY "Users update own automation_delivery_events"
    ON public.automation_delivery_events FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

REVOKE ALL ON public.automation_delivery_events
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, UPDATE ON public.automation_delivery_events TO authenticated;
GRANT ALL ON public.automation_delivery_events TO service_role;

COMMENT ON TABLE public.automation_delivery_events IS
    'Owner-private delivery-candidate decisions, suppression reasons, cost telemetry and future open events; contains no raw customer rows';

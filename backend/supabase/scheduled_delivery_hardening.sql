-- Scheduled report delivery telemetry and public-share lifecycle hardening.
-- Apply after automation_guardrails.sql and visualization_revisions_shares.sql.

ALTER TABLE public.automation_delivery_events
    ADD COLUMN IF NOT EXISTS delivery_token UUID,
    ADD COLUMN IF NOT EXISTS delivery_channel TEXT,
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS narration TEXT;

ALTER TABLE public.automation_delivery_events
    DROP CONSTRAINT IF EXISTS automation_delivery_events_event_type_check;
ALTER TABLE public.automation_delivery_events
    ADD CONSTRAINT automation_delivery_events_event_type_check
    CHECK (event_type IN (
        'previewed', 'eligible', 'suppressed', 'delivered', 'failed', 'opened', 'muted'
    ));
ALTER TABLE public.automation_delivery_events
    DROP CONSTRAINT IF EXISTS automation_delivery_events_delivery_channel_check;
ALTER TABLE public.automation_delivery_events
    ADD CONSTRAINT automation_delivery_events_delivery_channel_check
    CHECK (delivery_channel IS NULL OR delivery_channel IN ('email'));

CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_delivery_token
    ON public.automation_delivery_events(delivery_token)
    WHERE delivery_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_automation_delivery_status_created
    ON public.automation_delivery_events(event_type, created_at DESC);

ALTER TABLE public.visualization_report_shares
    ADD COLUMN IF NOT EXISTS max_views INTEGER
        CHECK (max_views IS NULL OR max_views BETWEEN 1 AND 1000000),
    ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0
        CHECK (access_count >= 0),
    ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_visualization_shares_expiry
    ON public.visualization_report_shares(expires_at)
    WHERE revoked_at IS NULL;

-- Keep Data API exposure explicit; RLS remains enabled by the parent migrations.
REVOKE ALL ON public.automation_delivery_events,
    public.visualization_report_shares
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, UPDATE ON public.automation_delivery_events TO authenticated;
GRANT ALL ON public.automation_delivery_events TO service_role;
GRANT SELECT, INSERT, DELETE ON public.visualization_report_shares TO authenticated;
GRANT ALL ON public.visualization_report_shares TO service_role;

COMMENT ON COLUMN public.automation_delivery_events.narration IS
    'Evidence-bounded scheduled narration; contains aggregate KPI metadata only';
COMMENT ON COLUMN public.visualization_report_shares.max_views IS
    'Optional read budget enforced by the backend in addition to expiry and revocation';

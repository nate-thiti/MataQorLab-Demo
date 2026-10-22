-- P1 dashboard idempotency, filter persistence, and share-view semantics.
-- Apply after visualization_reports.sql and scheduled_delivery_hardening.sql.

ALTER TABLE public.visualization_reports
    ADD COLUMN IF NOT EXISTS source_message_id UUID
    REFERENCES public.chat_messages(id) ON DELETE SET NULL;
ALTER TABLE public.visualization_reports
    ADD COLUMN IF NOT EXISTS filter_state JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(filter_state) = 'object');

CREATE UNIQUE INDEX IF NOT EXISTS idx_visualization_reports_source_message
    ON public.visualization_reports (user_id, source_message_id)
    WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visualization_reports_source_message_fk
    ON public.visualization_reports (source_message_id)
    WHERE source_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.visualization_share_view_sessions (
    share_id UUID NOT NULL
        REFERENCES public.visualization_report_shares(id) ON DELETE CASCADE,
    view_session_id UUID NOT NULL,
    first_viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (share_id, view_session_id)
);

CREATE INDEX IF NOT EXISTS idx_visualization_share_sessions_last_viewed
    ON public.visualization_share_view_sessions (last_viewed_at);

ALTER TABLE public.visualization_share_view_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "No browser access to share view sessions"
    ON public.visualization_share_view_sessions;
CREATE POLICY "No browser access to share view sessions"
    ON public.visualization_share_view_sessions
    FOR ALL TO authenticated
    USING (FALSE)
    WITH CHECK (FALSE);
REVOKE ALL ON public.visualization_share_view_sessions
    FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.visualization_share_view_sessions TO service_role;

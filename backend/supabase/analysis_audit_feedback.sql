-- Semantic metric registry and per-finding feedback for compute-first analysis.
-- Safe to re-run after chat_intelligence.sql.

CREATE TABLE IF NOT EXISTS public.semantic_metric_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_key TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    definition JSONB NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, dataset_key, metric_key)
);

CREATE INDEX IF NOT EXISTS idx_semantic_metric_definitions_user_dataset
    ON public.semantic_metric_definitions (user_id, dataset_key, updated_at DESC);

ALTER TABLE public.semantic_metric_definitions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own semantic metrics"
    ON public.semantic_metric_definitions;
CREATE POLICY "Users read own semantic metrics"
    ON public.semantic_metric_definitions FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users insert own semantic metrics"
    ON public.semantic_metric_definitions;
CREATE POLICY "Users insert own semantic metrics"
    ON public.semantic_metric_definitions FOR INSERT TO authenticated
    WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users update own semantic metrics"
    ON public.semantic_metric_definitions;
CREATE POLICY "Users update own semantic metrics"
    ON public.semantic_metric_definitions FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users delete own semantic metrics"
    ON public.semantic_metric_definitions;
CREATE POLICY "Users delete own semantic metrics"
    ON public.semantic_metric_definitions FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.semantic_metric_definitions TO authenticated;
GRANT ALL ON public.semantic_metric_definitions TO service_role;
REVOKE ALL ON public.semantic_metric_definitions FROM anon;

ALTER TABLE public.chat_quality_events
    DROP CONSTRAINT IF EXISTS chat_quality_events_event_type_check;
ALTER TABLE public.chat_quality_events
    ADD CONSTRAINT chat_quality_events_event_type_check
    CHECK (
        event_type IN (
            'response_generated',
            'user_feedback',
            'finding_feedback',
            'regenerated',
            'citation_opened'
        )
    );

DROP POLICY IF EXISTS "Users insert own chat feedback"
    ON public.chat_quality_events;
CREATE POLICY "Users insert own chat feedback"
    ON public.chat_quality_events FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND event_type IN (
            'user_feedback',
            'finding_feedback',
            'regenerated',
            'citation_opened'
        )
        AND (
            conversation_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.conversations conversation
                WHERE conversation.id = conversation_id
                  AND conversation.user_id = (SELECT auth.uid())
            )
        )
        AND (
            message_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM public.chat_messages message
                WHERE message.id = message_id
                  AND message.user_id = (SELECT auth.uid())
            )
        )
    );

COMMENT ON TABLE public.semantic_metric_definitions IS
    'User-owned, dataset-scoped semantic metric definitions executed by the backend';

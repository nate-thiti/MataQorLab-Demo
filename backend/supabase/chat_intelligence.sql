-- Intent/memory/evidence/quality support for the intelligent chat pipeline.
-- Safe to re-run. Apply after the core conversations/chat_messages tables exist.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS verification JSONB,
    ADD COLUMN IF NOT EXISTS model_used TEXT,
    ADD COLUMN IF NOT EXISTS response_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.chat_messages
    DROP CONSTRAINT IF EXISTS chat_messages_verification_is_object;
ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_verification_is_object
    CHECK (verification IS NULL OR jsonb_typeof(verification) = 'object');

ALTER TABLE public.chat_messages
    DROP CONSTRAINT IF EXISTS chat_messages_response_metadata_is_object;
ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_response_metadata_is_object
    CHECK (jsonb_typeof(response_metadata) = 'object');

CREATE TABLE IF NOT EXISTS public.chat_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('user', 'conversation', 'project', 'evidence')),
    memory_key TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    value JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(value) = 'object'),
    keywords TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, scope, memory_key)
);

CREATE INDEX IF NOT EXISTS idx_chat_memories_user_scope_updated
    ON public.chat_memories (user_id, scope, updated_at DESC);

ALTER TABLE public.chat_memories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own chat memories" ON public.chat_memories;
CREATE POLICY "Users read own chat memories"
    ON public.chat_memories FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users delete own chat memories" ON public.chat_memories;
CREATE POLICY "Users delete own chat memories"
    ON public.chat_memories FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users update own chat memories" ON public.chat_memories;
CREATE POLICY "Users update own chat memories"
    ON public.chat_memories FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

REVOKE INSERT ON public.chat_memories FROM anon, authenticated;
GRANT SELECT, UPDATE, DELETE ON public.chat_memories TO authenticated;
GRANT ALL ON public.chat_memories TO service_role;

CREATE TABLE IF NOT EXISTS public.chat_quality_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES public.chat_messages(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('response_generated', 'user_feedback', 'regenerated', 'citation_opened')
    ),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_quality_events_user_created
    ON public.chat_quality_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_quality_events_conversation
    ON public.chat_quality_events (conversation_id, created_at DESC)
    WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_quality_events_message
    ON public.chat_quality_events (message_id)
    WHERE message_id IS NOT NULL;

ALTER TABLE public.chat_quality_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own chat quality events" ON public.chat_quality_events;
CREATE POLICY "Users read own chat quality events"
    ON public.chat_quality_events FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users insert own chat feedback" ON public.chat_quality_events;
CREATE POLICY "Users insert own chat feedback"
    ON public.chat_quality_events FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND event_type IN ('user_feedback', 'regenerated', 'citation_opened')
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

REVOKE UPDATE, DELETE ON public.chat_quality_events FROM anon, authenticated;
GRANT SELECT, INSERT ON public.chat_quality_events TO authenticated;
GRANT ALL ON public.chat_quality_events TO service_role;

COMMENT ON TABLE public.chat_memories IS
    'Persistent memory scopes used to compact and personalize chat context';
COMMENT ON TABLE public.chat_quality_events IS
    'Per-response telemetry and explicit feedback for regression and routing evaluation';
COMMENT ON COLUMN public.chat_messages.response_metadata IS
    'Persistent intent, search queries, latency, and saved processing trace';

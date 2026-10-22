-- Weekly, exact-once AI analysis delivery into an owned MataQorLab conversation.
-- Apply after etl_workflows.sql, automation_guardrails.sql and
-- scheduled_delivery_hardening.sql.

ALTER TABLE public.etl_schedules
    ADD COLUMN IF NOT EXISTS chat_delivery_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS chat_delivery_weekday SMALLINT,
    ADD COLUMN IF NOT EXISTS chat_delivery_hour SMALLINT NOT NULL DEFAULT 9,
    ADD COLUMN IF NOT EXISTS chat_delivery_minute SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS chat_target_conversation_id UUID
        REFERENCES public.conversations(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS chat_source_dataset_key TEXT,
    ADD COLUMN IF NOT EXISTS chat_delivery_prompt TEXT;

ALTER TABLE public.etl_schedules
    DROP CONSTRAINT IF EXISTS etl_schedules_chat_delivery_weekday_check;
ALTER TABLE public.etl_schedules
    ADD CONSTRAINT etl_schedules_chat_delivery_weekday_check
    CHECK (chat_delivery_weekday IS NULL OR chat_delivery_weekday BETWEEN 1 AND 7);

ALTER TABLE public.etl_schedules
    DROP CONSTRAINT IF EXISTS etl_schedules_chat_delivery_hour_check;
ALTER TABLE public.etl_schedules
    ADD CONSTRAINT etl_schedules_chat_delivery_hour_check
    CHECK (chat_delivery_hour BETWEEN 0 AND 23);

ALTER TABLE public.etl_schedules
    DROP CONSTRAINT IF EXISTS etl_schedules_chat_delivery_minute_check;
ALTER TABLE public.etl_schedules
    ADD CONSTRAINT etl_schedules_chat_delivery_minute_check
    CHECK (chat_delivery_minute BETWEEN 0 AND 59);

ALTER TABLE public.etl_schedules
    DROP CONSTRAINT IF EXISTS etl_schedules_chat_delivery_fields_check;
ALTER TABLE public.etl_schedules
    ADD CONSTRAINT etl_schedules_chat_delivery_fields_check
    CHECK (
        NOT chat_delivery_enabled
        OR (
            schedule_kind = 'cron'
            AND chat_delivery_weekday IS NOT NULL
            AND chat_source_dataset_key IS NOT NULL
            AND length(chat_source_dataset_key) BETWEEN 1 AND 500
        )
    );

ALTER TABLE public.etl_schedules
    DROP CONSTRAINT IF EXISTS etl_schedules_chat_delivery_prompt_check;
ALTER TABLE public.etl_schedules
    ADD CONSTRAINT etl_schedules_chat_delivery_prompt_check
    CHECK (chat_delivery_prompt IS NULL OR length(chat_delivery_prompt) <= 1000);

CREATE INDEX IF NOT EXISTS idx_etl_schedules_chat_conversation
    ON public.etl_schedules(chat_target_conversation_id)
    WHERE chat_target_conversation_id IS NOT NULL;

-- A customer can send one source dataset to only one chat schedule. This also
-- prevents recipe-version duplicates because uniqueness follows dataset_key.
CREATE UNIQUE INDEX IF NOT EXISTS idx_etl_schedules_one_chat_per_dataset
    ON public.etl_schedules(user_id, chat_source_dataset_key)
    WHERE chat_delivery_enabled AND chat_source_dataset_key IS NOT NULL;

ALTER TABLE public.automation_delivery_events
    DROP CONSTRAINT IF EXISTS automation_delivery_events_delivery_channel_check;
ALTER TABLE public.automation_delivery_events
    ADD CONSTRAINT automation_delivery_events_delivery_channel_check
    CHECK (delivery_channel IS NULL OR delivery_channel IN ('email', 'chat'));

-- One eligible decision may result in one email and one chat delivery.
DROP INDEX IF EXISTS public.idx_automation_delivery_events_dedup;
CREATE UNIQUE INDEX idx_automation_delivery_events_dedup
    ON public.automation_delivery_events (
        schedule_id,
        fingerprint,
        event_type,
        COALESCE(delivery_channel, 'decision')
    )
    WHERE fingerprint IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.scheduled_chat_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    schedule_id UUID NOT NULL REFERENCES public.etl_schedules(id) ON DELETE CASCADE,
    run_id UUID REFERENCES public.etl_pipeline_runs(id) ON DELETE SET NULL,
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL CHECK (
        length(fingerprint) = 64 AND fingerprint ~ '^[0-9a-f]{64}$'
    ),
    message_id UUID REFERENCES public.chat_messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    UNIQUE (schedule_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_scheduled_chat_deliveries_user_created
    ON public.scheduled_chat_deliveries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduled_chat_deliveries_run
    ON public.scheduled_chat_deliveries(run_id)
    WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_scheduled_chat_deliveries_conversation
    ON public.scheduled_chat_deliveries(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduled_chat_deliveries_message
    ON public.scheduled_chat_deliveries(message_id)
    WHERE message_id IS NOT NULL;

ALTER TABLE public.scheduled_chat_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.scheduled_chat_deliveries
    FROM PUBLIC, anon, authenticated, service_role;
GRANT ALL ON public.scheduled_chat_deliveries TO service_role;

CREATE OR REPLACE FUNCTION public.deliver_scheduled_chat_message(
    p_user_id UUID,
    p_schedule_id UUID,
    p_run_id UUID,
    p_fingerprint TEXT,
    p_content TEXT,
    p_response_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(message_id UUID, created BOOLEAN)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_conversation_id UUID;
    v_delivery_id UUID;
    v_existing_message_id UUID;
    v_message_id UUID;
BEGIN
    IF p_content IS NULL OR length(trim(p_content)) = 0 OR length(p_content) > 20000 THEN
        RAISE EXCEPTION 'Scheduled chat content is invalid';
    END IF;
    IF p_fingerprint IS NULL OR p_fingerprint !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Scheduled chat fingerprint is invalid';
    END IF;

    SELECT schedule.chat_target_conversation_id
      INTO v_conversation_id
      FROM public.etl_schedules AS schedule
     WHERE schedule.id = p_schedule_id
       AND schedule.user_id = p_user_id
       AND schedule.enabled
       AND schedule.chat_delivery_enabled
     FOR UPDATE;

    IF v_conversation_id IS NULL THEN
        RAISE EXCEPTION 'Scheduled chat target is unavailable';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.conversations AS conversation
         WHERE conversation.id = v_conversation_id
           AND conversation.user_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'Scheduled chat target is not owned by this user';
    END IF;

    INSERT INTO public.scheduled_chat_deliveries (
        user_id, schedule_id, run_id, conversation_id, fingerprint
    )
    VALUES (
        p_user_id, p_schedule_id, p_run_id, v_conversation_id, p_fingerprint
    )
    ON CONFLICT (schedule_id, fingerprint) DO NOTHING
    RETURNING id INTO v_delivery_id;

    IF v_delivery_id IS NULL THEN
        SELECT delivery.message_id
          INTO v_existing_message_id
          FROM public.scheduled_chat_deliveries AS delivery
         WHERE delivery.schedule_id = p_schedule_id
           AND delivery.fingerprint = p_fingerprint;
        RETURN QUERY SELECT v_existing_message_id, FALSE;
        RETURN;
    END IF;

    INSERT INTO public.chat_messages (
        user_id, conversation_id, role, content, response_metadata
    )
    VALUES (
        p_user_id,
        v_conversation_id,
        'ai',
        p_content,
        COALESCE(p_response_metadata, '{}'::JSONB) || jsonb_build_object(
            'message_type', 'scheduled_analysis',
            'schedule_id', p_schedule_id,
            'run_id', p_run_id,
            'dataset_fingerprint', p_fingerprint
        )
    )
    RETURNING id INTO v_message_id;

    UPDATE public.scheduled_chat_deliveries
       SET message_id = v_message_id,
           delivered_at = NOW()
     WHERE id = v_delivery_id;

    RETURN QUERY SELECT v_message_id, TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.deliver_scheduled_chat_message(
    UUID, UUID, UUID, TEXT, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.deliver_scheduled_chat_message(
    UUID, UUID, UUID, TEXT, TEXT, JSONB
) TO service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_publication_tables
         WHERE pubname = 'supabase_realtime'
           AND schemaname = 'public'
           AND tablename = 'chat_messages'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.chat_messages;
    END IF;
END;
$$;

COMMENT ON TABLE public.scheduled_chat_deliveries IS
    'Backend-only exact-once ledger for weekly AI analysis messages';
COMMENT ON INDEX public.idx_etl_schedules_one_chat_per_dataset IS
    'Prevents one customer dataset from being scheduled into multiple chats';

-- Versioned Chat branches and idempotent generation persistence.
-- Safe to re-run. Apply after the core conversations/chat_messages tables exist.

CREATE TABLE IF NOT EXISTS public.chat_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    parent_branch_id UUID REFERENCES public.chat_branches(id) ON DELETE SET NULL,
    forked_from_message_id UUID REFERENCES public.chat_messages(id) ON DELETE SET NULL,
    branch_index INTEGER NOT NULL DEFAULT 1 CHECK (branch_index >= 1),
    title TEXT NOT NULL DEFAULT 'Main',
    is_root BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, user_id, conversation_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_branches_one_root
    ON public.chat_branches (conversation_id)
    WHERE is_root;
CREATE INDEX IF NOT EXISTS idx_chat_branches_conversation_created
    ON public.chat_branches (conversation_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_branches_conversation_version
    ON public.chat_branches (conversation_id, branch_index);
CREATE INDEX IF NOT EXISTS idx_chat_branches_user_created
    ON public.chat_branches (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_branches_parent
    ON public.chat_branches (parent_branch_id)
    WHERE parent_branch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_branches_fork_message
    ON public.chat_branches (forked_from_message_id)
    WHERE forked_from_message_id IS NOT NULL;

ALTER TABLE public.chat_branches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own chat branches" ON public.chat_branches;
CREATE POLICY "Users read own chat branches"
    ON public.chat_branches FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users create own chat branches" ON public.chat_branches;
CREATE POLICY "Users create own chat branches"
    ON public.chat_branches FOR INSERT TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND EXISTS (
            SELECT 1
            FROM public.conversations conversation
            WHERE conversation.id = conversation_id
              AND conversation.user_id = (SELECT auth.uid())
        )
    );

REVOKE ALL ON public.chat_branches FROM anon;
REVOKE ALL ON public.chat_branches FROM authenticated;
GRANT SELECT, INSERT ON public.chat_branches TO authenticated;
GRANT ALL ON public.chat_branches TO service_role;

ALTER TABLE public.conversations
    ADD COLUMN IF NOT EXISTS active_branch_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_active_branch_id_fkey'
          AND conrelid = 'public.conversations'::regclass
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_active_branch_id_fkey
            FOREIGN KEY (active_branch_id)
            REFERENCES public.chat_branches(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_active_branch
    ON public.conversations (active_branch_id)
    WHERE active_branch_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.validate_conversation_active_branch()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    IF NEW.active_branch_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM public.chat_branches branch
        WHERE branch.id = NEW.active_branch_id
          AND branch.conversation_id = NEW.id
          AND branch.user_id = NEW.user_id
    ) THEN
        RAISE EXCEPTION 'Conversation branch mismatch';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS validate_conversation_active_branch_trigger ON public.conversations;
CREATE TRIGGER validate_conversation_active_branch_trigger
BEFORE INSERT OR UPDATE OF active_branch_id ON public.conversations
FOR EACH ROW EXECUTE FUNCTION public.validate_conversation_active_branch();

REVOKE ALL ON FUNCTION public.validate_conversation_active_branch()
    FROM PUBLIC, anon, authenticated;

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS branch_id UUID,
    ADD COLUMN IF NOT EXISTS origin_message_id UUID,
    ADD COLUMN IF NOT EXISTS client_request_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_messages_origin_message_id_fkey'
          AND conrelid = 'public.chat_messages'::regclass
    ) THEN
        ALTER TABLE public.chat_messages
            ADD CONSTRAINT chat_messages_origin_message_id_fkey
            FOREIGN KEY (origin_message_id)
            REFERENCES public.chat_messages(id)
            ON DELETE SET NULL;
    END IF;
END $$;

INSERT INTO public.chat_branches (
    conversation_id,
    user_id,
    branch_index,
    title,
    is_root
)
SELECT conversation.id, conversation.user_id, 1, 'Main', true
FROM public.conversations conversation
WHERE NOT EXISTS (
    SELECT 1
    FROM public.chat_branches branch
    WHERE branch.conversation_id = conversation.id
      AND branch.is_root
);

UPDATE public.chat_messages message
SET branch_id = branch.id
FROM public.chat_branches branch
WHERE message.conversation_id = branch.conversation_id
  AND message.user_id = branch.user_id
  AND branch.is_root
  AND message.branch_id IS NULL;

UPDATE public.conversations conversation
SET active_branch_id = branch.id
FROM public.chat_branches branch
WHERE branch.conversation_id = conversation.id
  AND branch.user_id = conversation.user_id
  AND branch.is_root
  AND conversation.active_branch_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_messages_branch_owner_fkey'
          AND conrelid = 'public.chat_messages'::regclass
    ) THEN
        ALTER TABLE public.chat_messages
            ADD CONSTRAINT chat_messages_branch_owner_fkey
            FOREIGN KEY (branch_id, user_id, conversation_id)
            REFERENCES public.chat_branches(id, user_id, conversation_id)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_idempotent_generation
    ON public.chat_messages (user_id, branch_id, client_request_id, role)
    WHERE client_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_messages_branch_created
    ON public.chat_messages (branch_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_branch_owner
    ON public.chat_messages (branch_id, user_id, conversation_id)
    WHERE branch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_messages_origin
    ON public.chat_messages (origin_message_id)
    WHERE origin_message_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.assign_chat_message_branch()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_actor_id UUID := (SELECT auth.uid());
    v_branch_id UUID;
BEGIN
    IF NEW.conversation_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF v_actor_id IS NOT NULL AND v_actor_id <> NEW.user_id THEN
        RAISE EXCEPTION 'Message owner mismatch';
    END IF;

    IF NEW.branch_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.chat_branches branch
            WHERE branch.id = NEW.branch_id
              AND branch.conversation_id = NEW.conversation_id
              AND branch.user_id = NEW.user_id
        ) THEN
            RAISE EXCEPTION 'Message branch mismatch';
        END IF;
        RETURN NEW;
    END IF;

    SELECT conversation.active_branch_id
    INTO v_branch_id
    FROM public.conversations conversation
    WHERE conversation.id = NEW.conversation_id
      AND conversation.user_id = NEW.user_id;

    IF v_branch_id IS NULL THEN
        SELECT branch.id
        INTO v_branch_id
        FROM public.chat_branches branch
        WHERE branch.conversation_id = NEW.conversation_id
          AND branch.user_id = NEW.user_id
          AND branch.is_root
        LIMIT 1;
    END IF;

    IF v_branch_id IS NULL THEN
        INSERT INTO public.chat_branches (
            conversation_id, user_id, branch_index, title, is_root
        ) VALUES (
            NEW.conversation_id, NEW.user_id, 1, 'Main', true
        ) RETURNING id INTO v_branch_id;

        UPDATE public.conversations
        SET active_branch_id = v_branch_id
        WHERE id = NEW.conversation_id
          AND user_id = NEW.user_id;
    END IF;

    NEW.branch_id := v_branch_id;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS assign_chat_message_branch_trigger ON public.chat_messages;
CREATE TRIGGER assign_chat_message_branch_trigger
BEFORE INSERT ON public.chat_messages
FOR EACH ROW EXECUTE FUNCTION public.assign_chat_message_branch();

REVOKE ALL ON FUNCTION public.assign_chat_message_branch() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.ensure_chat_branch(p_conversation_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_user_id UUID := (SELECT auth.uid());
    v_branch_id UUID;
BEGIN
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.conversations conversation
        WHERE conversation.id = p_conversation_id
          AND conversation.user_id = v_user_id
    ) THEN
        RAISE EXCEPTION 'Conversation not found';
    END IF;

    SELECT conversation.active_branch_id
    INTO v_branch_id
    FROM public.conversations conversation
    WHERE conversation.id = p_conversation_id
      AND conversation.user_id = v_user_id;

    IF v_branch_id IS NULL THEN
        SELECT branch.id
        INTO v_branch_id
        FROM public.chat_branches branch
        WHERE branch.conversation_id = p_conversation_id
          AND branch.user_id = v_user_id
          AND branch.is_root
        LIMIT 1;
    END IF;

    IF v_branch_id IS NULL THEN
        BEGIN
            INSERT INTO public.chat_branches (
                conversation_id, user_id, branch_index, title, is_root
            ) VALUES (
                p_conversation_id, v_user_id, 1, 'Main', true
            ) RETURNING id INTO v_branch_id;
        EXCEPTION WHEN unique_violation THEN
            SELECT branch.id
            INTO v_branch_id
            FROM public.chat_branches branch
            WHERE branch.conversation_id = p_conversation_id
              AND branch.user_id = v_user_id
              AND branch.is_root
            LIMIT 1;
        END;
    END IF;

    UPDATE public.conversations
    SET active_branch_id = v_branch_id
    WHERE id = p_conversation_id
      AND user_id = v_user_id;

    RETURN v_branch_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.activate_chat_branch(
    p_conversation_id UUID,
    p_branch_id UUID
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_user_id UUID := (SELECT auth.uid());
BEGIN
    IF v_user_id IS NULL OR NOT EXISTS (
        SELECT 1
        FROM public.chat_branches branch
        WHERE branch.id = p_branch_id
          AND branch.conversation_id = p_conversation_id
          AND branch.user_id = v_user_id
    ) THEN
        RAISE EXCEPTION 'Branch not found';
    END IF;

    UPDATE public.conversations
    SET active_branch_id = p_branch_id
    WHERE id = p_conversation_id
      AND user_id = v_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Conversation not found';
    END IF;
    RETURN p_branch_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fork_chat_branch(
    p_conversation_id UUID,
    p_source_branch_id UUID,
    p_fork_message_id UUID,
    p_title TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_user_id UUID := (SELECT auth.uid());
    v_new_branch_id UUID;
    v_cutoff_at TIMESTAMPTZ;
    v_branch_index INTEGER;
BEGIN
    IF v_user_id IS NULL OR NOT EXISTS (
        SELECT 1
        FROM public.chat_branches branch
        WHERE branch.id = p_source_branch_id
          AND branch.conversation_id = p_conversation_id
          AND branch.user_id = v_user_id
    ) THEN
        RAISE EXCEPTION 'Source branch not found';
    END IF;

    SELECT message.created_at
    INTO v_cutoff_at
    FROM public.chat_messages message
    WHERE message.id = p_fork_message_id
      AND message.branch_id = p_source_branch_id
      AND message.conversation_id = p_conversation_id
      AND message.user_id = v_user_id;

    IF v_cutoff_at IS NULL THEN
        RAISE EXCEPTION 'Fork message not found';
    END IF;

    -- Serialize version allocation for concurrent Edit/Regenerate requests.
    PERFORM conversation.id
    FROM public.conversations conversation
    WHERE conversation.id = p_conversation_id
      AND conversation.user_id = v_user_id
    FOR UPDATE;

    SELECT COALESCE(MAX(branch.branch_index), 0) + 1
    INTO v_branch_index
    FROM public.chat_branches branch
    WHERE branch.conversation_id = p_conversation_id
      AND branch.user_id = v_user_id;

    INSERT INTO public.chat_branches (
        conversation_id,
        user_id,
        parent_branch_id,
        forked_from_message_id,
        branch_index,
        title,
        is_root
    ) VALUES (
        p_conversation_id,
        v_user_id,
        p_source_branch_id,
        p_fork_message_id,
        v_branch_index,
        COALESCE(NULLIF(BTRIM(p_title), ''), 'Version ' || v_branch_index::TEXT),
        false
    ) RETURNING id INTO v_new_branch_id;

    INSERT INTO public.chat_messages (
        user_id,
        conversation_id,
        branch_id,
        origin_message_id,
        role,
        content,
        created_at,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        web_sources,
        verification,
        model_used,
        response_metadata,
        client_request_id
    )
    SELECT
        message.user_id,
        message.conversation_id,
        v_new_branch_id,
        COALESCE(message.origin_message_id, message.id),
        message.role,
        message.content,
        message.created_at,
        message.prompt_tokens,
        message.completion_tokens,
        message.total_tokens,
        message.web_sources,
        message.verification,
        message.model_used,
        message.response_metadata,
        message.client_request_id
    FROM public.chat_messages message
    WHERE message.branch_id = p_source_branch_id
      AND message.conversation_id = p_conversation_id
      AND message.user_id = v_user_id
      AND (
          message.created_at < v_cutoff_at
          OR (message.created_at = v_cutoff_at AND message.id < p_fork_message_id)
      )
    ORDER BY message.created_at, message.id;

    UPDATE public.conversations
    SET active_branch_id = v_new_branch_id
    WHERE id = p_conversation_id
      AND user_id = v_user_id;

    RETURN v_new_branch_id;
END;
$$;

REVOKE ALL ON FUNCTION public.ensure_chat_branch(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.activate_chat_branch(UUID, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.fork_chat_branch(UUID, UUID, UUID, TEXT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.ensure_chat_branch(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.activate_chat_branch(UUID, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fork_chat_branch(UUID, UUID, UUID, TEXT) TO authenticated;

COMMENT ON TABLE public.chat_branches IS
    'Immutable conversation branches created by prompt edits or assistant regeneration.';
COMMENT ON COLUMN public.chat_messages.client_request_id IS
    'Browser-generated generation ID used with branch and role to prevent duplicate retry persistence.';
COMMENT ON COLUMN public.chat_messages.origin_message_id IS
    'Original message copied into a descendant branch for audit lineage.';

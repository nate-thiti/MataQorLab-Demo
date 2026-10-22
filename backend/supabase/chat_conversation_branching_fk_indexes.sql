-- Cover every foreign key introduced by chat_conversation_branching.sql.
-- This follow-up is required only where the base migration was applied before
-- these indexes were folded into the canonical migration.

CREATE INDEX IF NOT EXISTS idx_chat_branches_parent
    ON public.chat_branches (parent_branch_id)
    WHERE parent_branch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_branches_fork_message
    ON public.chat_branches (forked_from_message_id)
    WHERE forked_from_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_active_branch
    ON public.conversations (active_branch_id)
    WHERE active_branch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_branch_owner
    ON public.chat_messages (branch_id, user_id, conversation_id)
    WHERE branch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_origin
    ON public.chat_messages (origin_message_id)
    WHERE origin_message_id IS NOT NULL;

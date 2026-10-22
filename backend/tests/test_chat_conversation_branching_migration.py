from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "chat_conversation_branching.sql"
).read_text(encoding="utf-8")


def test_branch_table_is_private_and_uses_explicit_grants():
    assert "ALTER TABLE public.chat_branches ENABLE ROW LEVEL SECURITY" in MIGRATION
    assert "REVOKE ALL ON public.chat_branches FROM anon" in MIGRATION
    assert "REVOKE ALL ON public.chat_branches FROM authenticated" in MIGRATION
    assert "GRANT SELECT, INSERT ON public.chat_branches TO authenticated" in MIGRATION
    assert "(SELECT auth.uid()) = user_id" in MIGRATION


def test_branch_mutations_are_invoker_scoped_rpcs():
    assert "SECURITY DEFINER" not in MIGRATION
    assert MIGRATION.count("SECURITY INVOKER") >= 5
    assert "GRANT EXECUTE ON FUNCTION public.ensure_chat_branch(UUID) TO authenticated" in MIGRATION
    assert "GRANT EXECUTE ON FUNCTION public.activate_chat_branch(UUID, UUID) TO authenticated" in MIGRATION
    assert (
        "GRANT EXECUTE ON FUNCTION public.fork_chat_branch(UUID, UUID, UUID, TEXT) "
        "TO authenticated"
    ) in MIGRATION


def test_retry_persistence_is_idempotent_per_branch_and_role():
    assert "idx_chat_messages_idempotent_generation" in MIGRATION
    assert "(user_id, branch_id, client_request_id, role)" in MIGRATION
    assert "WHERE client_request_id IS NOT NULL" in MIGRATION


def test_fork_copies_only_the_transcript_prefix_with_lineage():
    assert "p_fork_message_id UUID" in MIGRATION
    assert "COALESCE(message.origin_message_id, message.id)" in MIGRATION
    assert "message.created_at < v_cutoff_at" in MIGRATION
    assert "UPDATE public.conversations\n    SET active_branch_id = v_new_branch_id" in MIGRATION


def test_message_trigger_assigns_legacy_writes_to_an_owned_branch():
    assert "CREATE TRIGGER assign_chat_message_branch_trigger" in MIGRATION
    assert "BEFORE INSERT ON public.chat_messages" in MIGRATION
    assert "branch.conversation_id = NEW.conversation_id" in MIGRATION
    assert "branch.user_id = NEW.user_id" in MIGRATION


def test_active_branch_and_concurrent_version_allocation_are_guarded():
    assert "idx_chat_branches_conversation_version" in MIGRATION
    assert "(conversation_id, branch_index)" in MIGRATION
    assert "CREATE TRIGGER validate_conversation_active_branch_trigger" in MIGRATION
    assert "branch.conversation_id = NEW.id" in MIGRATION
    assert "branch.user_id = NEW.user_id" in MIGRATION
    assert "FOR UPDATE" in MIGRATION


def test_every_branching_foreign_key_has_a_covering_index():
    assert "idx_chat_branches_parent" in MIGRATION
    assert "idx_chat_branches_fork_message" in MIGRATION
    assert "idx_conversations_active_branch" in MIGRATION
    assert "idx_chat_messages_branch_owner" in MIGRATION
    assert "idx_chat_messages_origin" in MIGRATION

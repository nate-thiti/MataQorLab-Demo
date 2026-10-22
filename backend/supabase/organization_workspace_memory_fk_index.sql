-- Cover the composite workspace/organization foreign key used by governed memory.
CREATE INDEX IF NOT EXISTS idx_governed_memories_workspace_organization
    ON public.governed_memories(workspace_id, organization_id);

-- One-way cleanup after switching analytical memory to verified computed facts.
-- This intentionally removes legacy free-form insight prose.

UPDATE public.chat_memories
SET
    summary = 'User question: ' || regexp_replace(
        split_part(summary, E'\nA:', 1),
        '^Q:\s*',
        ''
    ),
    updated_at = now()
WHERE scope = 'conversation'
  AND summary LIKE E'%\nA:%';

DELETE FROM public.chat_memories
WHERE scope = 'project'
  AND NOT (value ? 'computed_facts');

DELETE FROM public.analysis_insights_memory;

COMMENT ON TABLE public.analysis_insights_memory IS
    'Deprecated legacy prose memory. Runtime read/write paths are disabled; retained only for migration compatibility.';

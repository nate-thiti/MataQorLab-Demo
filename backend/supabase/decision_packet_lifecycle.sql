-- Ask → Prove → Pin decision packet state on visualization reports.
-- Safe to re-run. Application code falls back to dashboard_spec.decision_packet
-- when this column is not yet applied.

ALTER TABLE public.visualization_reports
    ADD COLUMN IF NOT EXISTS decision_packet JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'visualization_reports_decision_packet_object'
    ) THEN
        ALTER TABLE public.visualization_reports
            ADD CONSTRAINT visualization_reports_decision_packet_object
            CHECK (jsonb_typeof(decision_packet) = 'object');
    END IF;
END $$;

COMMENT ON COLUMN public.visualization_reports.decision_packet IS
    'Ask→Prove→Pin state: lifecycle, pins with evidence, insight actions, last prove snapshot/diff.';

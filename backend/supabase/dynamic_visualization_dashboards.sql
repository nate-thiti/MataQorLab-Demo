-- Adaptive BI dashboard configuration for private Visualization reports.
-- Apply after visualization_reports.sql.

ALTER TABLE public.visualization_reports
    ADD COLUMN IF NOT EXISTS source_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS dashboard_spec JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.visualization_reports
    DROP CONSTRAINT IF EXISTS visualization_reports_source_config_object,
    ADD CONSTRAINT visualization_reports_source_config_object
        CHECK (jsonb_typeof(source_config) = 'object'),
    DROP CONSTRAINT IF EXISTS visualization_reports_dashboard_spec_object,
    ADD CONSTRAINT visualization_reports_dashboard_spec_object
        CHECK (jsonb_typeof(dashboard_spec) = 'object');

-- Data API grants and owner RLS are already defined by visualization_reports.sql.
-- Repeat the explicit least-privilege grants so this migration is self-contained
-- for projects using the 2026 opt-in Data API exposure defaults.
REVOKE ALL ON TABLE
    public.visualization_reports,
    public.visualization_charts
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.visualization_reports,
    public.visualization_charts
    TO authenticated, service_role;

COMMENT ON COLUMN public.visualization_reports.source_config IS
    'Owner-validated file/API/SQL provenance used to rebuild an adaptive dashboard';
COMMENT ON COLUMN public.visualization_reports.dashboard_spec IS
    'Versioned adaptive BI filter, KPI, widget and layout specification';

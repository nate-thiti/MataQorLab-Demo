CREATE INDEX IF NOT EXISTS idx_customer_onboarding_first_dashboard
    ON public.customer_onboarding_progress (first_dashboard_id)
    WHERE first_dashboard_id IS NOT NULL;

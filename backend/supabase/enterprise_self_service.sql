-- Self-service Enterprise billing. price_monthly is the per-seat USD price.
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS subscription_seats INTEGER NOT NULL DEFAULT 1
    CHECK (subscription_seats BETWEEN 1 AND 500);

ALTER TABLE public.payment_history
    ADD COLUMN IF NOT EXISTS seat_count INTEGER NOT NULL DEFAULT 1
    CHECK (seat_count BETWEEN 1 AND 500);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_history_stripe_invoice_unique
    ON public.payment_history(stripe_invoice_id)
    WHERE stripe_invoice_id IS NOT NULL;

INSERT INTO public.plans (
    name,
    description,
    price_monthly,
    price_yearly,
    storage_limit_mb,
    message_limit,
    quota_description,
    has_priority_response
)
SELECT
    'Enterprise',
    'Self-service team plan billed per user, minimum 2 users',
    99,
    1188,
    2000,
    2000000,
    'Enterprise daily analysis quota with governed workspace features',
    true
WHERE NOT EXISTS (
    SELECT 1 FROM public.plans WHERE lower(name) = 'enterprise'
);

COMMENT ON COLUMN public.profiles.subscription_seats IS
    'Stripe subscription quantity; Enterprise checkout requires at least two seats';
COMMENT ON COLUMN public.payment_history.seat_count IS
    'Paid subscription seat quantity captured when the invoice was recorded';

CREATE OR REPLACE FUNCTION public._quota_limit_error(
    p_plan_name text,
    p_used_today bigint,
    p_used_week bigint,
    p_tokens bigint,
    p_daily_reset timestamptz,
    p_weekly_reset timestamptz,
    p_mode text DEFAULT 'check'
)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path = 'public'
AS $$
DECLARE
    v_plan_lower text := lower(COALESCE(p_plan_name, 'free'));
    v_limit_today bigint;
    v_limit_week bigint;
    v_used_today bigint := COALESCE(p_used_today, 0);
    v_used_week bigint := COALESCE(p_used_week, 0);
    v_tokens bigint := COALESCE(p_tokens, 0);
    v_for_increment boolean := lower(COALESCE(p_mode, 'check')) = 'increment';
BEGIN
    IF v_plan_lower LIKE '%enterprise%' THEN
        v_limit_today := 2000000;
        IF (v_for_increment AND v_used_today + v_tokens > v_limit_today)
           OR (NOT v_for_increment AND v_used_today >= v_limit_today) THEN
            RETURN jsonb_build_object(
                'status', 'error',
                'error', 'Quota Exceeded',
                'message', format(
                    'Daily limit of %s tokens reached (Enterprise).',
                    v_limit_today
                ),
                'used', v_used_today,
                'limit', v_limit_today,
                'reset_at', p_daily_reset
            );
        END IF;
        RETURN NULL;
    ELSIF v_plan_lower LIKE '%pro%' THEN
        v_limit_today := 1000000;
        IF (v_for_increment AND v_used_today + v_tokens > v_limit_today)
           OR (NOT v_for_increment AND v_used_today >= v_limit_today) THEN
            RETURN jsonb_build_object(
                'status', 'error',
                'error', 'Quota Exceeded',
                'message', format(
                    'Daily limit of %s tokens reached (Pro).',
                    v_limit_today
                ),
                'used', v_used_today,
                'limit', v_limit_today,
                'reset_at', p_daily_reset
            );
        END IF;
        RETURN NULL;
    ELSIF v_plan_lower LIKE '%plus%' THEN
        v_limit_today := 400000;
        v_limit_week := 2500000;
        IF (v_for_increment AND v_used_today + v_tokens > v_limit_today)
           OR (NOT v_for_increment AND v_used_today >= v_limit_today) THEN
            RETURN jsonb_build_object(
                'status', 'error',
                'error', 'Quota Exceeded',
                'message', format(
                    'Daily limit of %s tokens reached (Plus).',
                    v_limit_today
                ),
                'used', v_used_today,
                'limit', v_limit_today,
                'reset_at', p_daily_reset
            );
        END IF;
        IF (v_for_increment AND v_used_week + v_tokens > v_limit_week)
           OR (NOT v_for_increment AND v_used_week >= v_limit_week) THEN
            RETURN jsonb_build_object(
                'status', 'error',
                'error', 'Quota Exceeded',
                'message', format(
                    'Weekly limit of %s tokens reached (Plus).',
                    v_limit_week
                ),
                'used', v_used_week,
                'limit', v_limit_week,
                'reset_at', p_weekly_reset
            );
        END IF;
        RETURN NULL;
    ELSE
        v_limit_week := 200000;
        IF (v_for_increment AND v_used_week + v_tokens > v_limit_week)
           OR (NOT v_for_increment AND v_used_week >= v_limit_week) THEN
            RETURN jsonb_build_object(
                'status', 'error',
                'error', 'Quota Exceeded',
                'message', format(
                    'Weekly limit of %s tokens reached (Free).',
                    v_limit_week
                ),
                'used', v_used_week,
                'limit', v_limit_week,
                'reset_at', p_weekly_reset
            );
        END IF;
        RETURN NULL;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION private.check_user_message_quota(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    v_refreshed jsonb;
    v_plan_lower text;
    v_used_today bigint;
    v_used_week bigint;
    v_limit_today bigint;
    v_limit_week bigint;
    v_daily_reset timestamptz;
    v_weekly_reset timestamptz;
    v_error jsonb;
BEGIN
    PERFORM public._quota_assert_user(p_user_id);
    v_refreshed := public.refresh_profile_quota(p_user_id);
    v_plan_lower := lower(COALESCE(v_refreshed ->> 'plan_name', 'free'));
    v_used_today := (v_refreshed ->> 'used_today')::bigint;
    v_used_week := (v_refreshed ->> 'used_week')::bigint;
    v_daily_reset := (v_refreshed ->> 'daily_reset_at')::timestamptz;
    v_weekly_reset := (v_refreshed ->> 'weekly_reset_at')::timestamptz;

    v_error := public._quota_limit_error(
        v_refreshed ->> 'plan_name',
        v_used_today,
        v_used_week,
        0,
        v_daily_reset,
        v_weekly_reset,
        'check'
    );
    IF v_error IS NOT NULL THEN
        RETURN v_error;
    END IF;

    IF v_plan_lower LIKE '%enterprise%' THEN
        v_limit_today := 2000000;
        RETURN jsonb_build_object(
            'status', 'ok',
            'used', v_used_today,
            'limit', v_limit_today,
            'used_today', v_used_today,
            'used_week', v_used_week,
            'daily_reset_at', v_daily_reset,
            'weekly_reset_at', v_weekly_reset,
            'timezone', v_refreshed ->> 'timezone'
        );
    ELSIF v_plan_lower LIKE '%pro%' THEN
        v_limit_today := 1000000;
        RETURN jsonb_build_object(
            'status', 'ok',
            'used', v_used_today,
            'limit', v_limit_today,
            'used_today', v_used_today,
            'used_week', v_used_week,
            'daily_reset_at', v_daily_reset,
            'weekly_reset_at', v_weekly_reset,
            'timezone', v_refreshed ->> 'timezone'
        );
    ELSIF v_plan_lower LIKE '%plus%' THEN
        v_limit_today := 400000;
        v_limit_week := 2500000;
        RETURN jsonb_build_object(
            'status', 'ok',
            'used', v_used_today,
            'limit', v_limit_today,
            'used_today', v_used_today,
            'used_week', v_used_week,
            'used_week_limit', v_limit_week,
            'daily_reset_at', v_daily_reset,
            'weekly_reset_at', v_weekly_reset,
            'timezone', v_refreshed ->> 'timezone'
        );
    ELSE
        v_limit_week := 200000;
        RETURN jsonb_build_object(
            'status', 'ok',
            'used', v_used_week,
            'limit', v_limit_week,
            'used_today', v_used_today,
            'used_week', v_used_week,
            'daily_reset_at', v_daily_reset,
            'weekly_reset_at', v_weekly_reset,
            'timezone', v_refreshed ->> 'timezone'
        );
    END IF;
END;
$$;

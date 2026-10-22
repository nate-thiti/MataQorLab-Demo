-- Token quota RPC: reset (local timezone), check limits, increment usage atomically.
-- Run in Supabase SQL Editor after profiles_timezone.sql.

CREATE OR REPLACE FUNCTION public._quota_next_local_midnight(p_timezone text, p_days integer DEFAULT 1)
RETURNS timestamptz
LANGUAGE plpgsql
STABLE
SET search_path = public
AS $$
DECLARE
  tz text := COALESCE(NULLIF(trim(p_timezone), ''), 'UTC');
BEGIN
  BEGIN
    RETURN (
      ((NOW() AT TIME ZONE tz)::date + p_days)::timestamp AT TIME ZONE tz
    );
  EXCEPTION WHEN OTHERS THEN
    RETURN (
      ((NOW() AT TIME ZONE 'UTC')::date + p_days)::timestamp AT TIME ZONE 'UTC'
    );
  END;
END;
$$;

CREATE OR REPLACE FUNCTION public._quota_assert_user(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NOT NULL AND auth.uid() <> p_user_id THEN
    RAISE EXCEPTION 'forbidden' USING ERRCODE = '42501';
  END IF;
END;
$$;

-- Returns quota error jsonb, or NULL when within limits.
-- p_mode: 'check' (pre-send, >= limit) or 'increment' (used + p_tokens > limit)
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
SET search_path = public
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
  IF v_plan_lower LIKE '%pro%' THEN
    v_limit_today := 1000000;
    IF (v_for_increment AND v_used_today + v_tokens > v_limit_today)
       OR (NOT v_for_increment AND v_used_today >= v_limit_today) THEN
      RETURN jsonb_build_object(
        'status', 'error',
        'error', 'Quota Exceeded',
        'message', format('Daily limit of %s tokens reached (Pro).', v_limit_today),
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
        'message', format('Daily limit of %s tokens reached (Plus).', v_limit_today),
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
        'message', format('Weekly limit of %s tokens reached (Plus).', v_limit_week),
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
        'message', format('Weekly limit of %s tokens reached (Free).', v_limit_week),
        'used', v_used_week,
        'limit', v_limit_week,
        'reset_at', p_weekly_reset
      );
    END IF;
    RETURN NULL;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.refresh_profile_quota(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_row profiles%ROWTYPE;
  v_plan_name text;
  v_needs_daily boolean := false;
  v_needs_weekly boolean := false;
BEGIN
  PERFORM public._quota_assert_user(p_user_id);

  SELECT * INTO v_row
  FROM public.profiles
  WHERE id = p_user_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile_not_found' USING ERRCODE = 'P0002';
  END IF;

  SELECT name INTO v_plan_name
  FROM public.plans
  WHERE id = v_row.plan_id;

  v_plan_name := COALESCE(v_plan_name, 'Free');

  v_needs_daily := v_row.daily_reset_at IS NULL OR NOW() >= v_row.daily_reset_at;
  v_needs_weekly := v_row.weekly_reset_at IS NULL OR NOW() >= v_row.weekly_reset_at;

  IF v_needs_daily OR v_needs_weekly THEN
    UPDATE public.profiles
    SET
      tokens_used_today = CASE WHEN v_needs_daily THEN 0 ELSE tokens_used_today END,
      daily_reset_at = CASE
        WHEN v_needs_daily THEN public._quota_next_local_midnight(COALESCE(timezone, 'UTC'), 1)
        ELSE daily_reset_at
      END,
      tokens_used_this_week = CASE WHEN v_needs_weekly THEN 0 ELSE tokens_used_this_week END,
      weekly_reset_at = CASE
        WHEN v_needs_weekly THEN public._quota_next_local_midnight(COALESCE(timezone, 'UTC'), 7)
        ELSE weekly_reset_at
      END
    WHERE id = p_user_id
    RETURNING * INTO v_row;
  END IF;

  RETURN jsonb_build_object(
    'status', 'ok',
    'used_today', COALESCE(v_row.tokens_used_today, 0),
    'used_week', COALESCE(v_row.tokens_used_this_week, 0),
    'daily_reset_at', v_row.daily_reset_at,
    'weekly_reset_at', v_row.weekly_reset_at,
    'timezone', COALESCE(v_row.timezone, 'UTC'),
    'plan_name', COALESCE(v_plan_name, 'Free')
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.check_user_message_quota(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
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

  IF v_plan_lower LIKE '%pro%' THEN
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

CREATE OR REPLACE FUNCTION public.increment_profile_tokens(p_user_id uuid, p_tokens bigint)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_refreshed jsonb;
  v_row profiles%ROWTYPE;
  v_error jsonb;
BEGIN
  PERFORM public._quota_assert_user(p_user_id);

  IF p_tokens IS NULL OR p_tokens <= 0 THEN
    v_refreshed := public.refresh_profile_quota(p_user_id);
    RETURN jsonb_build_object(
      'status', 'ok',
      'used_today', (v_refreshed ->> 'used_today')::bigint,
      'used_week', (v_refreshed ->> 'used_week')::bigint,
      'tokens_added', 0,
      'timezone', v_refreshed ->> 'timezone'
    );
  END IF;

  v_refreshed := public.refresh_profile_quota(p_user_id);

  v_error := public._quota_limit_error(
    v_refreshed ->> 'plan_name',
    (v_refreshed ->> 'used_today')::bigint,
    (v_refreshed ->> 'used_week')::bigint,
    p_tokens,
    (v_refreshed ->> 'daily_reset_at')::timestamptz,
    (v_refreshed ->> 'weekly_reset_at')::timestamptz,
    'increment'
  );
  IF v_error IS NOT NULL THEN
    RETURN v_error;
  END IF;

  UPDATE public.profiles
  SET
    tokens_used_today = COALESCE(tokens_used_today, 0) + p_tokens,
    tokens_used_this_week = COALESCE(tokens_used_this_week, 0) + p_tokens
  WHERE id = p_user_id
  RETURNING * INTO v_row;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile_not_found' USING ERRCODE = 'P0002';
  END IF;

  RETURN jsonb_build_object(
    'status', 'ok',
    'used_today', COALESCE(v_row.tokens_used_today, 0),
    'used_week', COALESCE(v_row.tokens_used_this_week, 0),
    'tokens_added', p_tokens,
    'daily_reset_at', v_row.daily_reset_at,
    'weekly_reset_at', v_row.weekly_reset_at,
    'timezone', COALESCE(v_row.timezone, 'UTC')
  );
END;
$$;

REVOKE ALL ON FUNCTION public.refresh_profile_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.check_user_message_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.increment_profile_tokens(uuid, bigint) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.refresh_profile_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.check_user_message_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.increment_profile_tokens(uuid, bigint) TO authenticated, service_role;

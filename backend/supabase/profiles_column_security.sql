-- Keep quota mutations privileged without exposing SECURITY DEFINER functions
-- through the public Data API schema.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO authenticated, service_role;

ALTER FUNCTION public.refresh_profile_quota(uuid) SET SCHEMA private;
ALTER FUNCTION public.check_user_message_quota(uuid) SET SCHEMA private;
ALTER FUNCTION public.increment_profile_tokens(uuid, bigint) SET SCHEMA private;

ALTER FUNCTION private.refresh_profile_quota(uuid) SECURITY DEFINER;
ALTER FUNCTION private.check_user_message_quota(uuid) SECURITY DEFINER;
ALTER FUNCTION private.increment_profile_tokens(uuid, bigint) SECURITY DEFINER;

REVOKE ALL ON FUNCTION private.refresh_profile_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.check_user_message_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.increment_profile_tokens(uuid, bigint) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.refresh_profile_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.check_user_message_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.increment_profile_tokens(uuid, bigint) TO authenticated, service_role;

CREATE OR REPLACE FUNCTION public.refresh_profile_quota(p_user_id uuid)
RETURNS jsonb
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT private.refresh_profile_quota(p_user_id);
$$;

CREATE OR REPLACE FUNCTION public.check_user_message_quota(p_user_id uuid)
RETURNS jsonb
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT private.check_user_message_quota(p_user_id);
$$;

CREATE OR REPLACE FUNCTION public.increment_profile_tokens(
  p_user_id uuid,
  p_tokens bigint
)
RETURNS jsonb
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT private.increment_profile_tokens(p_user_id, p_tokens);
$$;

REVOKE ALL ON FUNCTION public.refresh_profile_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.check_user_message_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.increment_profile_tokens(uuid, bigint) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.refresh_profile_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.check_user_message_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.increment_profile_tokens(uuid, bigint) TO authenticated, service_role;

-- Prevent users from self-upgrading plans or rewriting their own quota counters.
-- Paid plan changes remain backend-only through verified Stripe webhooks.
REVOKE UPDATE ON TABLE public.profiles FROM anon, authenticated;
GRANT UPDATE (full_name, timezone) ON TABLE public.profiles TO authenticated;

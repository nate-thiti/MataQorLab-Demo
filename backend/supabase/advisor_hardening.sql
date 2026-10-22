-- Resolve Supabase Security/Performance Advisor findings.
-- Safe assumptions:
-- - chat token usage is recorded atomically by backend increment_profile_tokens RPC
-- - agent_sessions is backend-only and accessed with service_role
-- - avatars is a public bucket, so public object delivery does not require a broad SELECT policy

-- 1) Stop legacy double token accounting. The backend owns token increments.
DROP TRIGGER IF EXISTS on_chat_message_inserted ON public.chat_messages;
DROP FUNCTION IF EXISTS public.handle_message_token_increment();

-- 2) Lock down privileged functions and remove mutable search paths.
ALTER FUNCTION public.handle_new_user() SET search_path = '';
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.handle_new_user() TO service_role;

ALTER FUNCTION public.rls_auto_enable() SET search_path = 'pg_catalog';
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO service_role;

-- Dashboard aggregation can obey the caller's RLS instead of bypassing it.
ALTER FUNCTION public.get_dashboard_stats(uuid) SECURITY INVOKER;
ALTER FUNCTION public.get_dashboard_stats(uuid) SET search_path = '';
REVOKE ALL ON FUNCTION public.get_dashboard_stats(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_dashboard_stats(uuid) TO authenticated, service_role;

-- Quota RPCs only touch the signed-in user's RLS-protected profile.
ALTER FUNCTION public.refresh_profile_quota(uuid) SECURITY INVOKER;
ALTER FUNCTION public.check_user_message_quota(uuid) SECURITY INVOKER;
ALTER FUNCTION public.increment_profile_tokens(uuid, bigint) SECURITY INVOKER;
REVOKE ALL ON FUNCTION public.refresh_profile_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.check_user_message_quota(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.increment_profile_tokens(uuid, bigint) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.refresh_profile_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.check_user_message_quota(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.increment_profile_tokens(uuid, bigint) TO authenticated, service_role;

-- 3) agent_sessions is backend-only. Scope the policy to service_role.
DROP POLICY IF EXISTS "Service role full access agent_sessions"
ON public.agent_sessions;
CREATE POLICY "Service role full access agent_sessions"
ON public.agent_sessions
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
REVOKE ALL ON TABLE public.agent_sessions FROM anon, authenticated;

-- 4) Cache auth.uid() once per statement and scope ownership policies to signed-in users.
DROP POLICY IF EXISTS "Users read own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users read own analysis insights"
ON public.analysis_insights_memory FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users insert own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users insert own analysis insights"
ON public.analysis_insights_memory FOR INSERT TO authenticated
WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users delete own analysis insights" ON public.analysis_insights_memory;
CREATE POLICY "Users delete own analysis insights"
ON public.analysis_insights_memory FOR DELETE TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can manage their own API connections" ON public.api_connections;
CREATE POLICY "Users can manage their own API connections"
ON public.api_connections FOR ALL TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert their own chat messages" ON public.chat_messages;
CREATE POLICY "Users can insert their own chat messages"
ON public.chat_messages FOR INSERT TO authenticated
WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users can view their own chat messages" ON public.chat_messages;
CREATE POLICY "Users can view their own chat messages"
ON public.chat_messages FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users read own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users read own column mappings"
ON public.column_mappings_memory FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users insert own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users insert own column mappings"
ON public.column_mappings_memory FOR INSERT TO authenticated
WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users update own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users update own column mappings"
ON public.column_mappings_memory FOR UPDATE TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users delete own column mappings" ON public.column_mappings_memory;
CREATE POLICY "Users delete own column mappings"
ON public.column_mappings_memory FOR DELETE TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can manage their own conversations" ON public.conversations;
CREATE POLICY "Users can manage their own conversations"
ON public.conversations FOR ALL TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can manage their own SQL connections" ON public.database_connections;
CREATE POLICY "Users can manage their own SQL connections"
ON public.database_connections FOR ALL TO authenticated
USING ((SELECT auth.uid()) = user_id)
WITH CHECK ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own payment history" ON public.payment_history;
CREATE POLICY "Users can view own payment history"
ON public.payment_history FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
CREATE POLICY "Users can view own profile"
ON public.profiles FOR SELECT TO authenticated
USING ((SELECT auth.uid()) = id);
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile"
ON public.profiles FOR UPDATE TO authenticated
USING ((SELECT auth.uid()) = id)
WITH CHECK ((SELECT auth.uid()) = id);

-- 5) Public buckets serve object URLs without broad storage.objects listing policies.
DROP POLICY IF EXISTS "Public Access" ON storage.objects;
DROP POLICY IF EXISTS "Public Access 1oj01fe_0" ON storage.objects;

-- 6) Cover foreign keys used by ownership filters, joins, and chat history ordering.
CREATE INDEX IF NOT EXISTS idx_api_connections_user_id
ON public.api_connections (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created_at
ON public.chat_messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created_at
ON public.chat_messages (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_user_created_at
ON public.conversations (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_database_connections_user_id
ON public.database_connections (user_id);
CREATE INDEX IF NOT EXISTS idx_payment_history_user_id
ON public.payment_history (user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_plan_id
ON public.profiles (plan_id);

-- This index does not match the actual expiry cleanup query (which filters only expires_at).
DROP INDEX IF EXISTS public.idx_agent_sessions_user_expires;

-- 7) The browser may update display fields, but never billing/quota columns.
REVOKE UPDATE ON TABLE public.profiles FROM anon, authenticated;
GRANT UPDATE (full_name, timezone) ON TABLE public.profiles TO authenticated;

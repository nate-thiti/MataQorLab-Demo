-- Unified customer usage: all owned Storage objects plus customer-owned Postgres rows.
CREATE OR REPLACE FUNCTION private.customer_storage_usage(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
  v_storage bigint := 0;
  v_database bigint := 0;
  v_limit bigint := 0;
BEGIN
  SELECT COALESCE(sum((o.metadata->>'size')::bigint), 0)
  INTO v_storage
  FROM storage.objects o
  WHERE (o.bucket_id = 'business-data' AND (storage.foldername(o.name))[1] = p_user_id::text)
     OR (o.bucket_id = 'avatars' AND (storage.foldername(o.name))[1] = p_user_id::text);

  SELECT
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.profiles r WHERE r.id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.conversations r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_messages r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_memories r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.chat_quality_events r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.database_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.api_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.payment_history r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.agent_sessions r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.cloud_dataset_connections r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_recipes r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_pipeline_runs r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_schedules r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.etl_quality_alerts r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.analysis_insights_memory r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.column_mappings_memory r WHERE r.user_id = p_user_id), 0) +
    COALESCE((SELECT sum(pg_column_size(r)) FROM public.semantic_metric_definitions r WHERE r.user_id = p_user_id), 0)
  INTO v_database;

  SELECT COALESCE(pl.storage_limit_mb, 1)::bigint * 1024 * 1024
  INTO v_limit
  FROM public.profiles pr
  LEFT JOIN public.plans pl ON pl.id = pr.plan_id
  WHERE pr.id = p_user_id;

  v_limit := COALESCE(v_limit, 1024 * 1024);
  RETURN jsonb_build_object(
    'storage_bytes', v_storage,
    'database_bytes', v_database,
    'used_bytes', v_storage + v_database,
    'limit_bytes', v_limit,
    'remaining_bytes', greatest(0, v_limit - v_storage - v_database)
  );
END;
$$;

REVOKE ALL ON FUNCTION private.customer_storage_usage(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.customer_storage_usage(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.get_customer_storage_usage(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  IF (SELECT auth.uid()) IS DISTINCT FROM p_user_id AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'Not authorized' USING ERRCODE = '42501';
  END IF;
  RETURN private.customer_storage_usage(p_user_id);
END;
$$;

REVOKE ALL ON FUNCTION public.get_customer_storage_usage(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.get_customer_storage_usage(uuid) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_customer_storage_usage(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.enforce_customer_storage_quota(
  p_user_id uuid,
  p_additional_bytes bigint DEFAULT 0,
  p_replacing_path text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
  v_usage jsonb;
  v_replaced bigint := 0;
  v_projected bigint;
BEGIN
  IF (SELECT auth.uid()) IS DISTINCT FROM p_user_id AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'Not authorized' USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM public.profiles WHERE id = p_user_id FOR UPDATE;
  v_usage := private.customer_storage_usage(p_user_id);
  IF p_replacing_path IS NOT NULL THEN
    SELECT COALESCE((metadata->>'size')::bigint, 0)
    INTO v_replaced
    FROM storage.objects
    WHERE bucket_id = 'business-data' AND name = p_replacing_path
    LIMIT 1;
  END IF;
  v_projected := (v_usage->>'used_bytes')::bigint
    + greatest(0, COALESCE(p_additional_bytes, 0) - COALESCE(v_replaced, 0));
  IF v_projected > (v_usage->>'limit_bytes')::bigint THEN
    RAISE EXCEPTION 'Customer storage quota exceeded'
      USING ERRCODE = 'P0001',
            DETAIL = jsonb_build_object(
              'used_bytes', (v_usage->>'used_bytes')::bigint,
              'additional_bytes', COALESCE(p_additional_bytes, 0),
              'replaced_bytes', COALESCE(v_replaced, 0),
              'limit_bytes', (v_usage->>'limit_bytes')::bigint
            )::text;
  END IF;
  RETURN v_usage || jsonb_build_object('projected_bytes', v_projected);
END;
$$;

REVOKE ALL ON FUNCTION public.enforce_customer_storage_quota(uuid,bigint,text) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.enforce_customer_storage_quota(uuid,bigint,text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.enforce_customer_storage_quota(uuid,bigint,text) TO service_role;

-- Browser uploads now go through FastAPI, which performs the locked quota check.
DROP POLICY IF EXISTS "Users can upload own business data" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload their own avatar" ON storage.objects;

COMMENT ON FUNCTION public.get_customer_storage_usage(uuid) IS
  'Owner-only unified usage including all owned Storage objects and customer-owned Postgres rows';

CREATE OR REPLACE FUNCTION public.get_dashboard_stats(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
  v_usage jsonb;
  v_file_count integer;
  v_conv_count integer;
  v_daily_usage integer;
  v_chart_data jsonb;
BEGIN
  IF (SELECT auth.uid()) IS DISTINCT FROM p_user_id AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'Not authorized' USING ERRCODE = '42501';
  END IF;
  v_usage := private.customer_storage_usage(p_user_id);
  SELECT count(*) INTO v_file_count FROM storage.objects
  WHERE bucket_id = 'business-data' AND (storage.foldername(name))[1] = p_user_id::text;
  SELECT count(*) INTO v_conv_count FROM public.conversations WHERE user_id = p_user_id;
  SELECT count(*) INTO v_daily_usage FROM public.chat_messages
  WHERE user_id = p_user_id AND role = 'user' AND created_at >= current_date;
  SELECT jsonb_agg(d) INTO v_chart_data FROM (
    SELECT to_char(day, 'Dy') name,
      (SELECT count(*) FROM public.chat_messages
       WHERE user_id = p_user_id AND role = 'user' AND created_at::date = day) value
    FROM generate_series(current_date - interval '6 days', current_date, interval '1 day') day
    ORDER BY day
  ) d;
  RETURN jsonb_build_object(
    'files', v_file_count,
    'totalSize', (v_usage->>'used_bytes')::bigint,
    'storageBytes', (v_usage->>'storage_bytes')::bigint,
    'databaseBytes', (v_usage->>'database_bytes')::bigint,
    'limitBytes', (v_usage->>'limit_bytes')::bigint,
    'conversations', v_conv_count,
    'dailyUsage', v_daily_usage,
    'chartData', v_chart_data
  );
END;
$$;

REVOKE ALL ON FUNCTION public.get_dashboard_stats(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.get_dashboard_stats(uuid) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_dashboard_stats(uuid) TO service_role;

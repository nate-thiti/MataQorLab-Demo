-- REST API connection: multi-header + JSON request body (Postman-style)
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE public.api_connections
  ADD COLUMN IF NOT EXISTS request_headers jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS request_body jsonb DEFAULT NULL;

COMMENT ON COLUMN public.api_connections.request_headers IS
  'Array of {key, value} HTTP headers, e.g. x-api-key, x-secret-key, Authorization';

COMMENT ON COLUMN public.api_connections.request_body IS
  'JSON object sent as request body for POST/PUT/PATCH';

-- Backfill legacy single-header rows into request_headers
UPDATE public.api_connections
SET request_headers = jsonb_build_array(
  jsonb_build_object('key', auth_header_name, 'value', COALESCE(auth_header_value, ''))
)
WHERE (request_headers IS NULL OR request_headers = '[]'::jsonb)
  AND auth_header_name IS NOT NULL
  AND btrim(auth_header_name) <> '';

-- Add per-user IANA timezone for quota reset at local midnight.
-- Run in Supabase SQL Editor.

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'UTC';

COMMENT ON COLUMN profiles.timezone IS 'IANA timezone (e.g. Asia/Bangkok) for daily/weekly token quota reset at local midnight';

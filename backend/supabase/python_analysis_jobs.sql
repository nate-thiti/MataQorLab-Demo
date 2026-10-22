-- Private-to-the-backend Python analysis job queue.
-- The project uses PostgREST from the worker, so the table stays in public but
-- is not granted to browser roles. RLS is defense in depth; service_role is the
-- only role with direct privileges.

create table if not exists public.python_analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid null references public.conversations(id) on delete set null,
  dataset_key text not null check (length(dataset_key) between 1 and 500),
  dataset_version_hash text not null check (dataset_version_hash ~ '^[a-f0-9]{64}$'),
  code text not null check (octet_length(code) between 1 and 100000),
  code_hash text not null check (code_hash ~ '^[a-f0-9]{64}$'),
  package_manifest jsonb not null default '{}'::jsonb,
  package_manifest_hash text not null check (package_manifest_hash ~ '^[a-f0-9]{64}$'),
  approval_id text not null check (approval_id ~ '^pyapprove_[a-f0-9]{64}$'),
  expected_outputs jsonb not null default '[]'::jsonb,
  resource_limits jsonb not null default '{}'::jsonb,
  status text not null default 'awaiting_confirmation'
    check (status in ('awaiting_confirmation','queued','running','completed','failed','cancelled','expired')),
  result_manifest jsonb null,
  error_code text null,
  audit jsonb not null default '{}'::jsonb,
  confirmed_at timestamptz null,
  started_at timestamptz null,
  completed_at timestamptz null,
  expires_at timestamptz not null default (now() + interval '7 days'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists python_analysis_jobs_user_created_idx
  on public.python_analysis_jobs (user_id, created_at desc);
create index if not exists python_analysis_jobs_queue_idx
  on public.python_analysis_jobs (status, created_at)
  where status in ('queued','running');
create unique index if not exists python_analysis_jobs_one_active_per_user_idx
  on public.python_analysis_jobs (user_id)
  where status in ('queued','running');

alter table public.python_analysis_jobs enable row level security;
revoke all on table public.python_analysis_jobs from anon, authenticated;
grant select, insert, update, delete on table public.python_analysis_jobs to service_role;

drop policy if exists python_analysis_jobs_no_browser_access on public.python_analysis_jobs;
create policy python_analysis_jobs_no_browser_access
  on public.python_analysis_jobs
  as restrictive
  for all
  to anon, authenticated
  using (false)
  with check (false);

create or replace function public.set_python_analysis_jobs_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists python_analysis_jobs_updated_at on public.python_analysis_jobs;
create trigger python_analysis_jobs_updated_at
before update on public.python_analysis_jobs
for each row execute function public.set_python_analysis_jobs_updated_at();

revoke all on function public.set_python_analysis_jobs_updated_at() from public, anon, authenticated;
grant execute on function public.set_python_analysis_jobs_updated_at() to service_role;

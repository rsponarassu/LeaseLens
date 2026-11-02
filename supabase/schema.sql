-- ===========================================================================
--  LeaseLens - Supabase schema for accounts and saved reviews
-- ===========================================================================
--
--  Run this once in the Supabase dashboard: SQL Editor -> New query -> paste
--  -> Run. It is idempotent, so running it again after an upgrade is safe.
--
--  What lives here, and what deliberately does not:
--
--    lease_reviews   the *derived* result of an analysis: score, findings,
--                    explanations and counter-clauses. The uploaded PDF and
--                    the verbatim clause text are never written to this
--                    database - the client strips `findings[].raw_text`
--                    before it inserts a row, and the API only keeps the
--                    document in memory for the session TTL.
--
--  The browser talks to this table with the public anon key. That key is
--  safe to ship *because* of the row-level security policies below: without
--  them anyone holding it could read every tenant's history.
-- ===========================================================================

-- gen_random_uuid() is built in on Postgres 13+ (Supabase default).
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. Table
-- ---------------------------------------------------------------------------
create table if not exists public.lease_reviews (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    created_at      timestamptz not null default now(),

    -- Enough metadata to render the history list without parsing the report.
    file_name       text not null,
    page_count      integer not null default 0,
    overall_score   integer not null check (overall_score between 0 and 100),
    risk_level      text not null check (
                        risk_level in ('low', 'moderate', 'elevated', 'high', 'critical')
                    ),
    violation_count integer not null default 0,
    top_drivers     text[] not null default '{}',

    -- Identifies the in-memory session that can still re-render the annotated
    -- PDF. Null for demo leases, and useless once the session expires.
    session_id      text,
    -- Set when the review came from one of the three bundled demo leases.
    sample_id       text,

    -- The full AnalysisReport, so a saved review can be reopened without
    -- re-uploading the document. Clause text is already stripped.
    report          jsonb not null
);

comment on table public.lease_reviews is
    'Saved LeaseLens reviews. Derived findings only - no lease text, no PDF.';
comment on column public.lease_reviews.report is
    'AnalysisReport as returned by POST /api/v1/analyze, with findings[].raw_text blanked.';
comment on column public.lease_reviews.session_id is
    'In-memory annotation session; only valid for CACHE_TTL_SECONDS after the analysis.';

-- The history view always sorts by newest first for one user.
create index if not exists lease_reviews_user_created_idx
    on public.lease_reviews (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- 2. Row-level security
-- ---------------------------------------------------------------------------
alter table public.lease_reviews enable row level security;

-- Force it for the table owner too, so a misconfigured deploy cannot leak rows
-- through a privileged connection that forgot to filter by user_id.
alter table public.lease_reviews force row level security;

drop policy if exists "lease_reviews_select_own" on public.lease_reviews;
create policy "lease_reviews_select_own"
    on public.lease_reviews
    for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "lease_reviews_insert_own" on public.lease_reviews;
create policy "lease_reviews_insert_own"
    on public.lease_reviews
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists "lease_reviews_update_own" on public.lease_reviews;
create policy "lease_reviews_update_own"
    on public.lease_reviews
    for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists "lease_reviews_delete_own" on public.lease_reviews;
create policy "lease_reviews_delete_own"
    on public.lease_reviews
    for delete
    to authenticated
    using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 3. Grants
-- ---------------------------------------------------------------------------
-- Deliberately no grant for `anon`: a signed-out visitor has no history, and
-- the app says so in the interface instead of showing an empty list.
revoke all on public.lease_reviews from anon;
grant select, insert, update, delete on public.lease_reviews to authenticated;

-- ---------------------------------------------------------------------------
-- 4. Optional: make created_at authoritative
-- ---------------------------------------------------------------------------
-- The client sends no created_at, so the default already wins. This trigger
-- additionally stops a crafted request from back-dating a row.
create or replace function public.lease_reviews_stamp_created_at()
returns trigger
language plpgsql
as $$
begin
    new.created_at := now();
    return new;
end;
$$;

drop trigger if exists lease_reviews_stamp_created_at on public.lease_reviews;
create trigger lease_reviews_stamp_created_at
    before insert on public.lease_reviews
    for each row
    execute function public.lease_reviews_stamp_created_at();

-- ---------------------------------------------------------------------------
-- 5. Verify
-- ---------------------------------------------------------------------------
-- Expect: rowsecurity = true, forcerowsecurity = true, and four policies.
--
--   select relname, relrowsecurity, relforcerowsecurity
--     from pg_class where relname = 'lease_reviews';
--
--   select policyname, cmd from pg_policies
--    where tablename = 'lease_reviews' order by policyname;
--
-- Expect zero rows below (without a JWT there is no auth.uid() to match):
--
--   select count(*) from public.lease_reviews;
-- ===========================================================================

-- FOOTBALL AI INTELLIGENCE: secure initial Supabase schema.
-- Review before applying in the Supabase SQL Editor. Not automatically deployed.
-- Backend data import uses a server-side secret key only. Browser access is read-only
-- for public football information; favorites are authenticated-user owned.
create extension if not exists pgcrypto;

create table if not exists public.football_results (
  id uuid primary key, league text not null, played_on date not null,
  home_team text not null, away_team text not null,
  home_goals smallint not null check (home_goals between 0 and 30),
  away_goals smallint not null check (away_goals between 0 and 30),
  home_ht_goals smallint, away_ht_goals smallint,
  home_corners smallint, away_corners smallint,
  home_yellows smallint, away_yellows smallint,
  source text not null, imported_at timestamptz not null default now(),
  unique (league,played_on,home_team,away_team)
);
create index if not exists football_results_league_date_idx on public.football_results(league,played_on desc);

create table if not exists public.football_fixtures (
  id uuid primary key, league text not null, kickoff_at timestamptz not null,
  home_team text not null, away_team text not null,
  source text not null, imported_at timestamptz not null default now(),
  unique (league,kickoff_at,home_team,away_team)
);
create index if not exists football_fixtures_time_idx on public.football_fixtures(kickoff_at);

create table if not exists public.football_odds_snapshots (
  id uuid primary key default gen_random_uuid(),
  fixture_id uuid references public.football_fixtures(id),
  bookmaker text not null, market text not null, selection text not null,
  line numeric(7,2), decimal_odds numeric(9,4) not null check (decimal_odds > 1),
  observed_at timestamptz not null, source text not null,
  imported_at timestamptz not null default now()
);
create index if not exists football_odds_fixture_time_idx on public.football_odds_snapshots(fixture_id,observed_at desc);

create table if not exists public.football_models (
  version text primary key,
  algorithm text not null,
  trained_until timestamptz,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table if not exists public.football_prediction_runs (
  id uuid primary key default gen_random_uuid(),
  fixture_id uuid not null references public.football_fixtures(id),
  model_version text not null references public.football_models(version),
  observed_at timestamptz not null,
  training_cutoff timestamptz not null,
  data_quality jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (training_cutoff <= observed_at)
);
create table if not exists public.football_predictions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.football_prediction_runs(id),
  market text not null, selection text not null, line numeric(7,2),
  probability numeric(9,7) not null check (probability between 0 and 1),
  metadata jsonb not null default '{}'::jsonb
);
create index if not exists football_predictions_run_idx on public.football_predictions(run_id);

create table if not exists public.football_favorites (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  league text not null, team text not null,
  created_at timestamptz not null default now(),
  unique (user_id,league,team)
);

-- Explicit privileges and RLS for ALL public tables.
alter table public.football_results enable row level security;
alter table public.football_fixtures enable row level security;
alter table public.football_odds_snapshots enable row level security;
alter table public.football_models enable row level security;
alter table public.football_prediction_runs enable row level security;
alter table public.football_predictions enable row level security;
alter table public.football_favorites enable row level security;

revoke all on public.football_results, public.football_fixtures,
 public.football_odds_snapshots, public.football_models,
 public.football_prediction_runs, public.football_predictions,
 public.football_favorites from anon, authenticated;

grant select on public.football_results, public.football_fixtures,
 public.football_odds_snapshots, public.football_models,
 public.football_prediction_runs, public.football_predictions
 to anon, authenticated;
grant select, insert, delete on public.football_favorites to authenticated;

create policy "Public football results read" on public.football_results for select to anon, authenticated using (true);
create policy "Public fixtures read" on public.football_fixtures for select to anon, authenticated using (true);
create policy "Public odds read" on public.football_odds_snapshots for select to anon, authenticated using (true);
create policy "Public models read" on public.football_models for select to anon, authenticated using (true);
create policy "Public prediction runs read" on public.football_prediction_runs for select to anon, authenticated using (true);
create policy "Public predictions read" on public.football_predictions for select to anon, authenticated using (true);
create policy "Favorite owner reads" on public.football_favorites for select to authenticated using ((select auth.uid())=user_id);
create policy "Favorite owner inserts" on public.football_favorites for insert to authenticated with check ((select auth.uid())=user_id);
create policy "Favorite owner deletes" on public.football_favorites for delete to authenticated using ((select auth.uid())=user_id);

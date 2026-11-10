-- Apex Predictor — PostgreSQL schema (Supabase-compatible).
-- Everything that can change in F1 is data. Identities are permanent; numbers,
-- team names and assignments are time-dependent rows. Snapshots are never
-- overwritten: each prediction run is a new version.

create table seasons (
  year            int primary key,
  rules_version   text not null,              -- apex.rules.RuleSet.version
  rules_verified  boolean not null default false,
  major_reg_change boolean not null default false
);

create table drivers (
  driver_id    text primary key,              -- drv_*
  full_name    text not null,
  code         text,
  nationality  text,
  source_ids   jsonb not null default '{}'    -- {"jolpica": "...", "openf1": 12}
);

create table driver_number_history (
  driver_id text references drivers, season int references seasons, number int not null,
  primary key (driver_id, season)
);

create table teams (
  team_id      text primary key,              -- team_*
  name         text not null,
  predecessor  text references teams,         -- sale / rebrand lineage
  source_ids   jsonb not null default '{}'
);

create table team_aliases (
  team_id text references teams, alias text not null, first_season int, last_season int,
  primary key (team_id, alias)
);

create table circuits (
  circuit_id text primary key, name text, country text,
  circuit_type text, overtaking real, safety_car real
);

create table events (
  season int references seasons, round int, name text not null, circuit_id text references circuits,
  event_date date, has_sprint boolean not null default false,
  status text not null check (status in ('scheduled','completed','cancelled','postponed')),
  primary key (season, round)
);

create table sessions (
  session_id bigserial primary key, season int, round int, kind text check (kind in ('race','sprint','qualifying','sprint_qualifying')),
  scheduled_distance_laps int, completed_laps int,
  unique (season, round, kind), foreign key (season, round) references events
);

create table season_entries (               -- announced / confirmed lineups
  season int references seasons, team_id text references teams, driver_id text references drivers,
  status text check (status in ('announced','confirmed','withdrawn')), source text, noted_at timestamptz default now(),
  primary key (season, team_id, driver_id)
);

create table event_entries (                -- per-round participation (reserves, replacements)
  season int, round int, driver_id text references drivers, team_id text references teams, racing_number int,
  participation_status text check (participation_status in ('announced','confirmed','participated','withdrawn')),
  primary key (season, round, driver_id), foreign key (season, round) references events
);

create table session_results (
  session_id bigint references sessions, driver_id text references drivers, team_id text references teams,
  result_version int not null default 1,     -- amended classifications add a version
  grid int, position int, position_text text, points numeric(5,1) not null, status text, laps int,
  is_current boolean not null default true, amended_reason text, recorded_at timestamptz default now(),
  primary key (session_id, driver_id, result_version)
);

create table standings_snapshots (
  season int, after_round int, driver_id text references drivers, points numeric(6,1), position int,
  countback int[] not null,                  -- finishes by position for FIA countback
  primary key (season, after_round, driver_id)
);

create table performance_features (
  run_id bigint, driver_id text references drivers, team_id text references teams,
  skill real, team_strength real, form real, momentum real, dnf_risk real, skill_sd real,
  primary key (run_id, driver_id)
);

create table prediction_runs (
  run_id bigserial primary key, season int references seasons, after_round int, model_version text,
  n_sims int, seed int, data_hash text, config jsonb, created_at timestamptz default now(),
  snapshot_path text                          -- versioned JSON published to the site
);

create table driver_probabilities (
  run_id bigint references prediction_runs, driver_id text references drivers,
  title_probability double precision not null, expected_points real, position_dist real[],
  below_resolution boolean default false,
  primary key (run_id, driver_id)
);

create table championship_status (
  run_id bigint references prediction_runs, driver_id text references drivers,
  status text check (status in ('ALIVE','ELIMINATED','CLINCHED','CHAMPION')),
  max_points numeric(6,1), alive_if_all_finish boolean, tie_break_uncertain boolean,
  primary key (run_id, driver_id)
);

create table scenarios (
  scenario_id uuid primary key default gen_random_uuid(), base_run_id bigint references prediction_runs,
  conditions jsonb not null, n_sims int, result jsonb, created_at timestamptz default now()
);

create table ingestion_logs (
  id bigserial primary key, source text, endpoint text, fetched_at timestamptz default now(),
  ok boolean, http_status int, data_hash text, message text
);

create table identity_review_queue (
  id bigserial primary key, kind text, payload jsonb, resolved boolean default false, created_at timestamptz default now()
);

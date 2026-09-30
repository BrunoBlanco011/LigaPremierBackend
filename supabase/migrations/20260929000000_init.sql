-- =====================================================================
-- Liga Premier - esquema inicial
-- =====================================================================
-- El backend (FastAPI) accede con la service_role key, que ignora RLS.
-- RLS se habilita en todas las tablas SIN politicas para que la anon key
-- no pueda leer/escribir directamente: toda la autorizacion vive en la API.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- Tipos
-- ---------------------------------------------------------------------
create type public.user_role as enum ('admin', 'coach');
create type public.tournament_status as enum ('draft', 'active', 'finished', 'cancelled');
create type public.match_status as enum (
    'scheduled',    -- programado
    'in_progress',  -- en juego
    'finished',     -- finalizado
    'postponed',    -- pendiente / reprogramado
    'cancelled',    -- cancelado (lluvia, etc.) - no cuenta en la tabla
    'forfeit'       -- un equipo pierde por forfeit - cuenta en la tabla
);

-- ---------------------------------------------------------------------
-- updated_at automatico
-- ---------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- ---------------------------------------------------------------------
-- Perfiles (1:1 con auth.users)
-- ---------------------------------------------------------------------
create table public.profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    email       text,
    full_name   text,
    role        public.user_role not null default 'coach',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- Todo usuario nuevo nace como 'coach'. El rol admin solo se asigna desde
-- la API (por otro admin) o manualmente en SQL: nunca desde el signup.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.profiles (id, email, full_name)
    values (new.id, new.email, new.raw_user_meta_data ->> 'full_name');
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- Torneos
-- ---------------------------------------------------------------------
create table public.tournaments (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    season        text,
    category      text,
    description   text,
    start_date    date,
    end_date      date,
    status        public.tournament_status not null default 'draft',
    points_win    smallint not null default 2 check (points_win >= 0),
    points_draw   smallint not null default 1 check (points_draw >= 0),
    points_loss   smallint not null default 0 check (points_loss >= 0),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint tournaments_dates_chk check (end_date is null or start_date is null or end_date >= start_date)
);

-- ---------------------------------------------------------------------
-- Equipos (pertenecen a un torneo)
-- ---------------------------------------------------------------------
create table public.teams (
    id              uuid primary key default gen_random_uuid(),
    tournament_id   uuid not null references public.tournaments (id) on delete cascade,
    name            text not null,
    coach_name      text,
    coach_user_id   uuid references public.profiles (id) on delete set null,
    logo_url        text,
    logo_path       text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create unique index teams_tournament_name_uq on public.teams (tournament_id, lower(name));
create index teams_coach_user_idx on public.teams (coach_user_id);

-- ---------------------------------------------------------------------
-- Jugadores
-- ---------------------------------------------------------------------
create table public.players (
    id              uuid primary key default gen_random_uuid(),
    team_id         uuid not null references public.teams (id) on delete cascade,
    full_name       text not null,
    jersey_number   smallint check (jersey_number between 0 and 999),
    position        text,
    birth_date      date,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index players_team_idx on public.players (team_id);
-- No puede haber dos jugadores activos con el mismo numero en un equipo
create unique index players_team_jersey_uq
    on public.players (team_id, jersey_number)
    where is_active and jersey_number is not null;

-- ---------------------------------------------------------------------
-- Jornadas
-- ---------------------------------------------------------------------
create table public.rounds (
    id              uuid primary key default gen_random_uuid(),
    tournament_id   uuid not null references public.tournaments (id) on delete cascade,
    number          smallint not null check (number > 0),
    name            text,
    start_date      date,
    end_date        date,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    constraint rounds_tournament_number_uq unique (tournament_id, number),
    constraint rounds_dates_chk check (end_date is null or start_date is null or end_date >= start_date)
);

-- ---------------------------------------------------------------------
-- Partidos
-- ---------------------------------------------------------------------
create table public.matches (
    id                      uuid primary key default gen_random_uuid(),
    tournament_id           uuid not null references public.tournaments (id) on delete cascade,
    round_id                uuid references public.rounds (id) on delete set null,
    home_team_id            uuid not null references public.teams (id) on delete cascade,
    away_team_id            uuid not null references public.teams (id) on delete cascade,
    scheduled_at            timestamptz,
    venue                   text,
    status                  public.match_status not null default 'scheduled',
    home_score              smallint check (home_score >= 0),
    away_score              smallint check (away_score >= 0),
    forfeit_loser_team_id   uuid references public.teams (id) on delete set null,
    notes                   text,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    constraint matches_distinct_teams_chk check (home_team_id <> away_team_id),
    constraint matches_forfeit_team_chk check (
        forfeit_loser_team_id is null
        or forfeit_loser_team_id in (home_team_id, away_team_id)
    )
);
create index matches_tournament_idx on public.matches (tournament_id);
create index matches_round_idx on public.matches (round_id);
create index matches_home_idx on public.matches (home_team_id);
create index matches_away_idx on public.matches (away_team_id);

-- ---------------------------------------------------------------------
-- Ajustes manuales a la tabla (multas, sanciones, puntos extra)
-- ---------------------------------------------------------------------
create table public.standing_adjustments (
    id              uuid primary key default gen_random_uuid(),
    tournament_id   uuid not null references public.tournaments (id) on delete cascade,
    team_id         uuid not null references public.teams (id) on delete cascade,
    points          smallint not null,
    reason          text not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index standing_adjustments_tournament_idx on public.standing_adjustments (tournament_id);

-- ---------------------------------------------------------------------
-- Estadisticas por jugador por partido
-- ---------------------------------------------------------------------
create table public.player_match_stats (
    id              uuid primary key default gen_random_uuid(),
    match_id        uuid not null references public.matches (id) on delete cascade,
    player_id       uuid not null references public.players (id) on delete cascade,
    attended        boolean not null default true,
    touchdowns      smallint not null default 0 check (touchdowns >= 0),
    td_passes       smallint not null default 0 check (td_passes >= 0),
    interceptions   smallint not null default 0 check (interceptions >= 0),
    sacks           smallint not null default 0 check (sacks >= 0),
    tackles         smallint not null default 0 check (tackles >= 0),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    constraint player_match_stats_uq unique (match_id, player_id)
);
create index player_match_stats_player_idx on public.player_match_stats (player_id);

-- ---------------------------------------------------------------------
-- Triggers updated_at
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
    foreach t in array array[
        'profiles', 'tournaments', 'teams', 'players', 'rounds',
        'matches', 'standing_adjustments', 'player_match_stats'
    ] loop
        execute format(
            'create trigger %1$s_set_updated_at before update on public.%1$s
             for each row execute function public.set_updated_at()', t);
        execute format('alter table public.%s enable row level security', t);
    end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- Storage: bucket publico para logos de equipos
-- ---------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('team-logos', 'team-logos', true)
on conflict (id) do nothing;

-- =====================================================================
-- Iteracion 3: modelo de club
--
--  clubs    = equipo permanente (nombre, logo, entrenador, coach, jugadores)
--  teams    = inscripcion de un club a un torneo. Partidos, tabla, ajustes y
--             finanzas siguen apuntando a `teams`, asi cada torneo conserva
--             su historial.
--  players  = pertenecen al club y se conservan entre temporadas.
--  player_match_stats.team_id = inscripcion con la que se jugo el partido
--             (si el jugador cambia de club, su historial no se mezcla).
--
-- Migra los datos existentes: crea un club por cada nombre de equipo distinto.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Clubes
-- ---------------------------------------------------------------------
create table public.clubs (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    coach_name      text,
    coach_user_id   uuid references public.profiles (id) on delete set null,
    logo_url        text,
    logo_path       text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create unique index clubs_name_uq on public.clubs (lower(name));
create index clubs_coach_user_idx on public.clubs (coach_user_id);

create trigger clubs_set_updated_at before update on public.clubs
    for each row execute function public.set_updated_at();
alter table public.clubs enable row level security;

-- Un club por nombre (se conservan los datos del equipo mas reciente)
insert into public.clubs (name, coach_name, coach_user_id, logo_url, logo_path)
select distinct on (lower(name)) name, coach_name, coach_user_id, logo_url, logo_path
from public.teams
order by lower(name), created_at desc;

-- ---------------------------------------------------------------------
-- teams -> inscripcion de un club a un torneo
-- ---------------------------------------------------------------------
alter table public.teams add column club_id uuid references public.clubs (id) on delete restrict;
update public.teams t set club_id = c.id from public.clubs c where lower(c.name) = lower(t.name);
alter table public.teams alter column club_id set not null;

-- ---------------------------------------------------------------------
-- Jugadores -> pertenecen al club
-- ---------------------------------------------------------------------
alter table public.players add column club_id uuid references public.clubs (id) on delete cascade;
update public.players p set club_id = t.club_id from public.teams t where t.id = p.team_id;

-- Estadisticas: guardar la inscripcion con la que se jugo
alter table public.player_match_stats add column team_id uuid references public.teams (id) on delete cascade;
update public.player_match_stats s set team_id = p.team_id from public.players p where p.id = s.player_id;
alter table public.player_match_stats alter column team_id set not null;
create index player_match_stats_team_idx on public.player_match_stats (team_id);

-- Si un club tenia el mismo numero en dos torneos, se deja activo solo el mas reciente
update public.players p set is_active = false
where p.is_active and p.jersey_number is not null and exists (
    select 1 from public.players q
    where q.club_id = p.club_id and q.jersey_number = p.jersey_number and q.is_active
      and (q.created_at, q.id) > (p.created_at, p.id)
);

drop index public.players_team_jersey_uq;
alter table public.players drop column team_id;
alter table public.players alter column club_id set not null;
create index players_club_idx on public.players (club_id);
create unique index players_club_jersey_uq
    on public.players (club_id, jersey_number)
    where is_active and jersey_number is not null;

-- ---------------------------------------------------------------------
-- Limpiar columnas que ahora viven en el club
-- ---------------------------------------------------------------------
drop index public.teams_tournament_name_uq;
drop index public.teams_coach_user_idx;
alter table public.teams
    drop column name,
    drop column coach_name,
    drop column coach_user_id,
    drop column logo_url,
    drop column logo_path;
alter table public.teams add constraint teams_tournament_club_uq unique (tournament_id, club_id);
create index teams_club_idx on public.teams (club_id);

-- ---------------------------------------------------------------------
-- Vista de lectura: inscripcion + datos del club
-- ---------------------------------------------------------------------
create view public.team_details with (security_invoker = true) as
select
    t.id,
    t.tournament_id,
    t.club_id,
    c.name,
    c.logo_url,
    c.coach_name,
    c.coach_user_id,
    t.created_at,
    t.updated_at
from public.teams t
join public.clubs c on c.id = t.club_id;

-- La vista solo la usa el backend (service_role)
revoke all on public.team_details from anon, authenticated;

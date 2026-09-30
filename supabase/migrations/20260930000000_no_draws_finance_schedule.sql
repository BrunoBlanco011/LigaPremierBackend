-- =====================================================================
-- Iteracion 2
--  - En tocho no hay empates: se juega tiempo extra
--  - Jugador: solo nombre y numero de jersey
--  - Jornadas: equipo que descansa (BYE) al generar el rol de juegos
--  - Modulo de finanzas (solo admin): inscripciones, multas, abonos
-- =====================================================================

-- ---------------------------------------------------------------------
-- Sin empates
-- ---------------------------------------------------------------------
alter table public.tournaments drop column points_draw;

alter table public.matches
    add constraint matches_no_draw_chk check (
        status <> 'finished'
        or home_score is null
        or away_score is null
        or home_score <> away_score
    );

-- ---------------------------------------------------------------------
-- Jugador simplificado
-- ---------------------------------------------------------------------
alter table public.players
    drop column position,
    drop column birth_date;

-- ---------------------------------------------------------------------
-- BYE por jornada
-- ---------------------------------------------------------------------
alter table public.rounds
    add column bye_team_id uuid references public.teams (id) on delete set null;

-- ---------------------------------------------------------------------
-- Finanzas
-- ---------------------------------------------------------------------
create type public.finance_movement_type as enum (
    'registration_fee',  -- inscripcion (cargo)
    'fine',              -- multa (cargo)
    'other_charge',      -- otro cargo
    'payment'            -- abono (reduce el adeudo)
);

create table public.finance_movements (
    id              uuid primary key default gen_random_uuid(),
    tournament_id   uuid not null references public.tournaments (id) on delete cascade,
    team_id         uuid not null references public.teams (id) on delete cascade,
    type            public.finance_movement_type not null,
    amount          numeric(10, 2) not null check (amount > 0),
    description     text,
    occurred_on     date not null default current_date,
    match_id        uuid references public.matches (id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index finance_movements_tournament_idx on public.finance_movements (tournament_id);
create index finance_movements_team_idx on public.finance_movements (team_id);

create trigger finance_movements_set_updated_at before update on public.finance_movements
    for each row execute function public.set_updated_at();
alter table public.finance_movements enable row level security;

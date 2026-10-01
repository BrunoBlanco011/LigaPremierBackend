-- =====================================================================
-- Invitaciones de club: link temporal (24h por defecto) para que los
-- jugadores se den de alta solos en la plantilla de su club.
-- El coach (o admin) genera el token; el registro publico lo consume.
-- =====================================================================

create table public.club_invites (
    id           uuid primary key default gen_random_uuid(),
    club_id      uuid not null references public.clubs (id) on delete cascade,
    token        text not null unique,
    expires_at   timestamptz not null,
    created_by   uuid references public.profiles (id) on delete set null,
    created_at   timestamptz not null default now()
);
create index club_invites_club_idx on public.club_invites (club_id);

-- RLS sin politicas: todo el acceso pasa por el backend (service_role).
alter table public.club_invites enable row level security;

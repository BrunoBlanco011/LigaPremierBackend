-- =====================================================================
-- Fecha de nacimiento opcional del jugador.
-- Solo la ven el admin y el coach del club (la API la oculta al publico).
-- =====================================================================

alter table public.players add column birth_date date;

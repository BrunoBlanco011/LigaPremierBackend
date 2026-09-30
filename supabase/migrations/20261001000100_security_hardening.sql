-- =====================================================================
-- Endurecimiento (recomendaciones del Security/Performance Advisor)
-- =====================================================================

-- search_path fijo en funciones
create or replace function public.set_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- handle_new_user solo debe correr como trigger, nunca via /rest/v1/rpc
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- Indices para llaves foraneas sin cubrir
create index if not exists finance_movements_match_idx on public.finance_movements (match_id);
create index if not exists matches_forfeit_loser_idx on public.matches (forfeit_loser_team_id);
create index if not exists rounds_bye_team_idx on public.rounds (bye_team_id);
create index if not exists standing_adjustments_team_idx on public.standing_adjustments (team_id);

-- Nota: "RLS enabled, no policy" es intencional. El backend usa la
-- service_role key; la anon key no debe poder leer ni escribir las tablas.

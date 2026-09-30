from supabase import Client

from app.domain.entities import (
    Club,
    FinanceMovement,
    Match,
    Player,
    PlayerMatchStats,
    Profile,
    Round,
    StandingAdjustment,
    Team,
    Tournament,
)
from app.domain.repositories import Repositories
from app.infrastructure.repositories.supabase_repository import SupabaseRepository


def build_supabase_repositories(client: Client) -> Repositories:
    return Repositories(
        profiles=SupabaseRepository(client, "profiles", Profile),
        tournaments=SupabaseRepository(client, "tournaments", Tournament),
        clubs=SupabaseRepository(client, "clubs", Club),
        teams=SupabaseRepository(client, "teams", Team, read_table="team_details"),
        players=SupabaseRepository(client, "players", Player),
        rounds=SupabaseRepository(client, "rounds", Round),
        matches=SupabaseRepository(client, "matches", Match),
        adjustments=SupabaseRepository(client, "standing_adjustments", StandingAdjustment),
        player_stats=SupabaseRepository(client, "player_match_stats", PlayerMatchStats),
        finance=SupabaseRepository(client, "finance_movements", FinanceMovement),
    )

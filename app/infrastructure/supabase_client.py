from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.core.config import get_settings


@lru_cache
def get_service_client() -> Client:
    """Cliente con service_role: ignora RLS. Solo se usa del lado del servidor."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )


def new_anon_client() -> Client:
    """Cliente desechable con la anon key (para login sin contaminar el cliente de servicio)."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Liga Premier API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = []

    supabase_url: str
    supabase_anon_key: str = ""
    supabase_service_role_key: str
    supabase_jwt_secret: str = ""

    team_logos_bucket: str = "team-logos"
    max_logo_size_mb: int = 2

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

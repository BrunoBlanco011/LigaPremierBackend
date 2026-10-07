from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

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

    # ---------------------------------------------------------- seguridad
    # Hosts aceptados en la cabecera Host (vacio = cualquiera; en produccion configuralo)
    allowed_hosts: Annotated[list[str], NoDecode] = []
    # /docs, /redoc y /openapi.json. Vacio: activos fuera de produccion
    docs_enabled: bool | None = None
    # Confiar en X-Forwarded-For para obtener la IP real (solo detras de un proxy propio)
    trust_proxy_headers: bool = False
    # Tamano maximo del cuerpo de una peticion (los logos tienen su propio limite)
    max_request_body_mb: int = 5
    # Peticiones por minuto por IP a toda la API
    rate_limit_per_minute: int = 300
    # Intentos de login fallidos permitidos por IP+correo en la ventana
    login_max_attempts: int = 5
    login_window_seconds: int = 900

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def show_docs(self) -> bool:
        return not self.is_production if self.docs_enabled is None else self.docs_enabled

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

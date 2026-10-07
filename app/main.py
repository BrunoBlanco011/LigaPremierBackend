import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, TooManyRequestsError
from app.core.middleware import BodySizeLimitMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import LoginThrottle

logger = logging.getLogger("app")


def _configure_logging() -> None:
    # Sin esto los INFO de la bitacora (logger "app.audit") no se escriben en ningun lado
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx registra cada consulta a Supabase con su URL completa: solo advertencias
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    if "*" in settings.cors_origins and settings.is_production:
        raise RuntimeError("CORS_ORIGINS='*' no esta permitido en produccion: lista los dominios del frontend")
    if settings.is_production and not settings.allowed_hosts:
        logger.warning("ALLOWED_HOSTS esta vacio: se acepta cualquier cabecera Host")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="API para administrar los torneos de tocho bandera de la Liga Premier.",
        docs_url="/docs" if settings.show_docs else None,
        redoc_url="/redoc" if settings.show_docs else None,
        openapi_url="/openapi.json" if settings.show_docs else None,
    )
    app.state.login_throttle = LoginThrottle(settings.login_max_attempts, settings.login_window_seconds)

    # El ultimo middleware agregado es el mas externo:
    # cabeceras de seguridad -> CORS -> hosts -> rate limit -> tamano del cuerpo -> app
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_mb * 1024 * 1024)
    if settings.rate_limit_per_minute > 0:
        app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute,
                           trust_proxy_headers=settings.trust_proxy_headers)
    if settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    if settings.cors_origins or not settings.is_production:
        # La API usa tokens Bearer en la cabecera Authorization (no cookies): no hace falta allow_credentials.
        # En desarrollo, Vite puede usar cualquier puerto (5173/5174/5175…): se acepta
        # cualquier localhost/127.0.0.1 por regex para no romper el CORS.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+" if not settings.is_production else None,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["Retry-After"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        headers = None
        if exc.status_code == 401:
            headers = {"WWW-Authenticate": "Bearer"}
        elif isinstance(exc, TooManyRequestsError):
            headers = {"Retry-After": str(exc.retry_after)}
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Nunca se devuelven trazas ni mensajes internos al cliente
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})

    @app.get("/health", tags=["Sistema"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

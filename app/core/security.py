"""Validacion de los JWT emitidos por Supabase Auth."""

from functools import lru_cache
from uuid import UUID

import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().supabase_jwks_url, cache_keys=True, lifespan=3600)


def decode_access_token(token: str) -> UUID:
    """Valida firma, expiracion y audiencia; devuelve el id del usuario (claim `sub`)."""
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthenticationError("Token HS256 recibido pero SUPABASE_JWT_SECRET no esta configurado")
            payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        else:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=_ASYMMETRIC_ALGORITHMS, audience="authenticated")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("El token ha expirado") from exc
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise AuthenticationError("Token invalido") from exc

    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Token sin usuario valido") from exc

"""Excepciones de dominio/aplicacion.

Las capas internas lanzan estas excepciones sin saber nada de HTTP; la capa
API las traduce a respuestas HTTP en un solo lugar (ver app/main.py).
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, entity: str, entity_id: object | None = None) -> None:
        detail = f"{entity} no encontrado" if entity_id is None else f"{entity} '{entity_id}' no encontrado"
        super().__init__(detail)


class ValidationError(AppError):
    status_code = 422


class ConflictError(AppError):
    status_code = 409


class AuthenticationError(AppError):
    status_code = 401


class PermissionDeniedError(AppError):
    status_code = 403


class TooManyRequestsError(AppError):
    status_code = 429

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after

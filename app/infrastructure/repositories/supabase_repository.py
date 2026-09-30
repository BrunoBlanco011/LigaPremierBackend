"""Implementacion generica del puerto `Repository` sobre Supabase (PostgREST)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Generic, Iterator, TypeVar
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from supabase import Client

from app.core.exceptions import AppError, ConflictError, ValidationError

T = TypeVar("T", bound=BaseModel)

# https://www.postgresql.org/docs/current/errcodes-appendix.html
_PG_ERRORS: dict[str, tuple[type[AppError], str]] = {
    "23505": (ConflictError, "Ya existe un registro con esos datos"),
    "23503": (ValidationError, "Referencia invalida a otro registro"),
    "23514": (ValidationError, "Los datos no cumplen las reglas de validacion"),
    "23502": (ValidationError, "Falta un campo obligatorio"),
    "22P02": (ValidationError, "Formato de dato invalido"),
}


@contextmanager
def translate_errors() -> Iterator[None]:
    try:
        yield
    except APIError as exc:
        error_cls, message = _PG_ERRORS.get(exc.code or "", (AppError, "Error de base de datos"))
        detail = f"{message}: {exc.details or exc.message}" if (exc.details or exc.message) else message
        raise error_cls(detail) from exc


def _json(data: Any) -> Any:
    """UUID, date, datetime y Enum -> tipos JSON aceptados por PostgREST."""
    return to_jsonable_python(data)


class SupabaseRepository(Generic[T]):
    def __init__(self, client: Client, table: str, model: type[T]) -> None:
        self.client = client
        self.table = table
        self.model = model

    def _query(self):
        return self.client.table(self.table)

    def _parse(self, rows: list[dict[str, Any]]) -> list[T]:
        return [self.model.model_validate(row) for row in rows]

    def get(self, entity_id: UUID) -> T | None:
        with translate_errors():
            response = self._query().select("*").eq("id", str(entity_id)).limit(1).execute()
        rows = self._parse(response.data)
        return rows[0] if rows else None

    def list(
        self,
        *,
        filters: Mapping[str, Any] | None = None,
        in_filters: Mapping[str, Sequence[Any]] | None = None,
        order_by: Sequence[str] = (),
    ) -> list[T]:
        query = self._query().select("*")
        for column, value in (filters or {}).items():
            query = query.is_(column, "null") if value is None else query.eq(column, _json(value))
        for column, values in (in_filters or {}).items():
            if not values:
                return []
            query = query.in_(column, _json(list(values)))
        for column in order_by:
            desc = column.startswith("-")
            query = query.order(column.lstrip("-"), desc=desc, nullsfirst=False)
        with translate_errors():
            response = query.execute()
        return self._parse(response.data)

    def create(self, data: Mapping[str, Any]) -> T:
        with translate_errors():
            response = self._query().insert(_json(dict(data))).execute()
        return self._parse(response.data)[0]

    def create_many(self, rows: Sequence[Mapping[str, Any]]) -> list[T]:
        if not rows:
            return []
        with translate_errors():
            response = self._query().insert(_json([dict(r) for r in rows])).execute()
        return self._parse(response.data)

    def update(self, entity_id: UUID, data: Mapping[str, Any]) -> T | None:
        with translate_errors():
            response = self._query().update(_json(dict(data))).eq("id", str(entity_id)).execute()
        rows = self._parse(response.data)
        return rows[0] if rows else None

    def delete(self, entity_id: UUID) -> bool:
        with translate_errors():
            response = self._query().delete().eq("id", str(entity_id)).execute()
        return bool(response.data)

    def upsert_many(self, rows: Sequence[Mapping[str, Any]], on_conflict: Sequence[str]) -> list[T]:
        if not rows:
            return []
        with translate_errors():
            response = self._query().upsert(_json([dict(r) for r in rows]), on_conflict=",".join(on_conflict)).execute()
        return self._parse(response.data)

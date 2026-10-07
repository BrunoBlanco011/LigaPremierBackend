"""Modulo de finanzas: todos los endpoints requieren rol admin."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminActor, Finance
from app.application.dto import FinanceMovementCreate, FinanceMovementUpdate, RegistrationFeeCreate
from app.application.read_models import FinanceSummary
from app.domain.entities import FinanceMovement
from app.domain.enums import FinanceMovementType

router = APIRouter(tags=["Finanzas (admin)"])
audit = logging.getLogger("app.audit")


@router.get("/tournaments/{tournament_id}/finance/summary", response_model=FinanceSummary,
            summary="Estado de cuenta por equipo (inscripcion + multas - abonos = adeudo)")
def finance_summary(tournament_id: UUID, _: AdminActor, service: Finance):
    return service.summary(tournament_id)


@router.get("/tournaments/{tournament_id}/finance/movements", response_model=list[FinanceMovement])
def list_movements(
    tournament_id: UUID,
    _: AdminActor,
    service: Finance,
    team_id: UUID | None = None,
    movement_type: Annotated[FinanceMovementType | None, Query(alias="type")] = None,
):
    return service.list_movements(tournament_id, team_id=team_id, movement_type=movement_type)


@router.post("/tournaments/{tournament_id}/finance/movements", response_model=FinanceMovement,
             status_code=status.HTTP_201_CREATED, summary="Registrar cargo (inscripcion, multa, otro) o abono")
def create_movement(tournament_id: UUID, data: FinanceMovementCreate, actor: AdminActor, service: Finance):
    movement = service.create(tournament_id, data)
    audit.info("finanzas: alta movimiento=%s monto=%s por=%s", movement.id, movement.amount, actor.id)
    return movement


@router.post("/tournaments/{tournament_id}/finance/registration-fees", response_model=list[FinanceMovement],
             status_code=status.HTTP_201_CREATED,
             summary="Cargar la inscripcion a todos los equipos que aun no la tengan")
def charge_registration_fees(tournament_id: UUID, data: RegistrationFeeCreate, actor: AdminActor, service: Finance):
    movements = service.charge_registration_fees(tournament_id, data)
    audit.info("finanzas: inscripciones torneo=%s cargos=%s por=%s", tournament_id, len(movements), actor.id)
    return movements


@router.patch("/finance/movements/{movement_id}", response_model=FinanceMovement)
def update_movement(movement_id: UUID, data: FinanceMovementUpdate, actor: AdminActor, service: Finance):
    movement = service.update(movement_id, data)
    audit.info("finanzas: cambio movimiento=%s campos=%s por=%s", movement_id, sorted(data.changes()), actor.id)
    return movement


@router.delete("/finance/movements/{movement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movement(movement_id: UUID, actor: AdminActor, service: Finance):
    service.delete(movement_id)
    audit.info("finanzas: baja movimiento=%s por=%s", movement_id, actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

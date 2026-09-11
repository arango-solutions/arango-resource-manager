"""The ArangoDeployment tier editor - the correct way to resize the database."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ClientsDep, SettingsDep
from app.api.v1.actions import _blocked
from app.models.actions import ActionResult, DatabaseScaleRequest
from app.services import arangodeployment
from app.services import inventory as inventory_service
from app.services.actions import ActionBlocked
from app.store.state import get_store

router = APIRouter(prefix="/database", tags=["database"])


@router.get("", response_model=arangodeployment.DatabaseStatus)
def database_status(clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    try:
        return arangodeployment.status(clients, settings)
    except ActionBlocked as exc:
        return _blocked(exc, dry_run=True)


@router.post("/scale", response_model=ActionResult)
def database_scale(  # noqa: ANN201
    request: DatabaseScaleRequest, clients: ClientsDep, settings: SettingsDep
):
    try:
        plan = arangodeployment.plan_scale(clients, settings, request.tier, request.count)
        plan = arangodeployment.execute(clients, settings, plan, request.tier, request.dry_run)
    except ActionBlocked as exc:
        return _blocked(exc, request.dry_run)

    if request.dry_run:
        return ActionResult(executed=False, dry_run=True, plan=plan)

    get_store().append_history(
        {
            "action": "database_scale",
            "kind": "ArangoDeployment",
            "name": plan.name,
            "from_replicas": plan.current_replicas,
            "to_replicas": plan.target_replicas,
            "dry_run": False,
            "result": "ok",
        }
    )
    inventory_service.invalidate()
    return ActionResult(executed=True, dry_run=False, plan=plan)

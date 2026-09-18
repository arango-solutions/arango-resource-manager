"""Mutating routes.

Every one of them plans first, then executes. A refusal returns a structured
reason plus a remediation, so the UI can explain rather than just fail.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.api.deps import ClientsDep, SettingsDep
from app.models.actions import (
    ActionPlan,
    ActionRecord,
    ActionResult,
    ActionType,
    PodDeleteRequest,
    ScaleRequest,
    ServiceKillRequest,
    WorkloadRequest,
)
from app.services import actions as action_service
from app.services import inventory as inventory_service
from app.store.state import get_store

router = APIRouter(prefix="/actions", tags=["actions"])

_STATUS_FOR_REASON = {
    "read_only": 403,
    "protected": 409,
    "guarded": 409,
    "database_locked": 409,
    "tier_immutable": 409,
    "not_found": 404,
    "invalid": 422,
}


def _blocked(exc: action_service.ActionBlocked, dry_run: bool) -> JSONResponse:
    result = ActionResult(
        executed=False,
        dry_run=dry_run,
        blocked_reason=exc.reason,
        detail=exc.detail,
        remediation=exc.remediation,
    )
    return JSONResponse(
        status_code=_STATUS_FOR_REASON.get(exc.reason, 409),
        content=result.model_dump(),
    )


def _run(clients: ClientsDep, settings: SettingsDep, plan: ActionPlan, dry_run: bool):  # noqa: ANN202
    return action_service.execute(clients, settings, get_store(), plan, dry_run)


@router.post("/scale", response_model=ActionResult)
def scale(request: ScaleRequest, clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_scale(
            snapshot, settings, request.kind, request.name, request.replicas
        )
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/stop", response_model=ActionResult)
def stop(request: WorkloadRequest, clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    """Scale to zero, remembering the previous count so it can be restored."""
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_scale(
            snapshot, settings, request.kind, request.name, 0, action=ActionType.STOP
        )
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/restore", response_model=ActionResult)
def restore(request: WorkloadRequest, clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_restore(
            snapshot, settings, get_store(), request.kind, request.name
        )
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/restart", response_model=ActionResult)
def restart(request: WorkloadRequest, clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_restart(snapshot, settings, request.kind, request.name)
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/pods/{name}/delete", response_model=ActionResult)
def delete_pod(  # noqa: ANN201
    name: str, request: PodDeleteRequest, clients: ClientsDep, settings: SettingsDep
):
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_delete_pod(
            snapshot, settings, name, force=request.force, container=request.container
        )
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/kill", response_model=ActionResult)
def kill(request: WorkloadRequest, clients: ClientsDep, settings: SettingsDep):  # noqa: ANN201
    """Scale to 0 and force-delete current pods, so the service dies immediately."""
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_kill(snapshot, settings, request.kind, request.name)
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.post("/services/{name}/kill", response_model=ActionResult)
def kill_service(  # noqa: ANN201
    name: str, request: ServiceKillRequest, clients: ClientsDep, settings: SettingsDep
):
    """Kill every actionable workload under a service group."""
    try:
        snapshot = inventory_service.get_snapshot(clients)
        plan = action_service.plan_kill_service(snapshot, settings, name)
        return _run(clients, settings, plan, request.dry_run)
    except action_service.ActionBlocked as exc:
        return _blocked(exc, request.dry_run)


@router.get("/stopped", response_model=dict)
def stopped(clients: ClientsDep) -> dict:
    """Workloads this tool stopped, and what to restore each one to."""
    namespace = clients.namespace
    prefix = f"{namespace}/"
    return {
        key[len(prefix) :]: value
        for key, value in get_store().all_stopped().items()
        if key.startswith(prefix)
    }


@router.get("/history", response_model=list[ActionRecord])
def history(limit: int = Query(100, ge=1, le=500)) -> list[ActionRecord]:
    return [ActionRecord(**entry) for entry in get_store().history(limit)]

"""Read routes over the namespace snapshot.

Every route is a plain `def`, not `async def`: the Kubernetes client is
blocking, so Starlette runs these in its threadpool. Mixing in `async def`
would block the event loop.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ClientsDep
from app.models.inventory import (
    InventorySnapshot,
    PodDetail,
    PodSummary,
    ServiceDetail,
    ServiceGroup,
    WorkloadSummary,
)
from app.services import inventory as inventory_service

router = APIRouter(tags=["inventory"])

SORT_KEYS = {
    "name": lambda p: p.name,
    "uptime": lambda p: p.age_seconds or 0,
    "restarts": lambda p: p.restart_count,
    "cpu": lambda p: p.resources.usage.cpu_cores or -1.0,
    "memory": lambda p: p.resources.usage.memory_bytes or -1,
}


@router.get("/snapshot", response_model=InventorySnapshot)
def snapshot(clients: ClientsDep) -> InventorySnapshot:
    """The whole namespace in one response, as the pages see it."""
    return inventory_service.get_snapshot(clients)


@router.get("/services", response_model=list[ServiceGroup])
def list_services(clients: ClientsDep) -> list[ServiceGroup]:
    return inventory_service.get_snapshot(clients).services


@router.get("/services/{name}", response_model=ServiceDetail)
def get_service(name: str, clients: ClientsDep) -> ServiceDetail:
    snap = inventory_service.get_snapshot(clients)
    detail = inventory_service.build_detail(snap, name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No service named {name!r}.")
    return detail


@router.get("/workloads", response_model=list[WorkloadSummary])
def list_workloads(
    clients: ClientsDep,
    service: str | None = None,
    kind: str | None = None,
    protection: str | None = None,
) -> list[WorkloadSummary]:
    workloads = inventory_service.get_snapshot(clients).workloads
    if service:
        workloads = [w for w in workloads if w.service == service]
    if kind:
        workloads = [w for w in workloads if w.kind == kind]
    if protection:
        workloads = [w for w in workloads if w.protection.level == protection]
    return workloads


@router.get("/pods", response_model=list[PodSummary])
def list_pods(
    clients: ClientsDep,
    service: str | None = None,
    workload: str | None = None,
    phase: str | None = None,
    sort: str = Query("name", pattern="^(name|uptime|restarts|cpu|memory)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> list[PodSummary]:
    pods = inventory_service.get_snapshot(clients).pods
    if service:
        pods = [p for p in pods if p.service == service]
    if workload:
        pods = [p for p in pods if p.workload and p.workload.name == workload]
    if phase:
        pods = [p for p in pods if p.phase.lower() == phase.lower()]
    return sorted(pods, key=SORT_KEYS[sort], reverse=order == "desc")


@router.get("/pods/{name}", response_model=PodDetail)
def get_pod(name: str, clients: ClientsDep) -> PodDetail:
    detail = inventory_service.get_pod_detail(clients, name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No pod named {name!r}.")
    return detail

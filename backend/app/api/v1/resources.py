"""Capacity: what is used, what is reserved, and what can be reclaimed."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ClientsDep, SettingsDep
from app.models.resources import (
    Budget,
    NamespaceOverview,
    ResourceReport,
    UnboundedPod,
    WasteItem,
)
from app.services import inventory as inventory_service
from app.services import metrics as metrics_service
from app.services import rollup

router = APIRouter(tags=["resources"])


@router.get("/namespace/overview", response_model=NamespaceOverview)
def namespace_overview(clients: ClientsDep, settings: SettingsDep) -> NamespaceOverview:
    snapshot = inventory_service.get_snapshot(clients)
    return rollup.overview(
        snapshot,
        settings,
        quotas=snapshot.resource_quotas,
        metrics_available=metrics_service.is_available(),
    )


@router.get("/resources/rollup", response_model=list[ResourceReport])
def resource_rollup(
    clients: ClientsDep,
    scope: str = Query("service", pattern="^(namespace|service|workload)$"),
) -> list[ResourceReport]:
    snapshot = inventory_service.get_snapshot(clients)
    if scope == "namespace":
        return [rollup.namespace_report(snapshot)]
    if scope == "workload":
        return rollup.workload_reports(snapshot)
    return rollup.service_reports(snapshot)


@router.get("/resources/waste", response_model=list[WasteItem])
def resource_waste(
    clients: ClientsDep,
    settings: SettingsDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[WasteItem]:
    return rollup.waste(inventory_service.get_snapshot(clients), settings, limit=limit)


@router.get("/resources/unbounded", response_model=list[UnboundedPod])
def unbounded(clients: ClientsDep) -> list[UnboundedPod]:
    """Pods with a container that has no limit, and so no ceiling at all."""
    return rollup.unbounded_pods(inventory_service.get_snapshot(clients))


@router.get("/resources/budget", response_model=Budget)
def budget(clients: ClientsDep, settings: SettingsDep) -> Budget:
    snapshot = inventory_service.get_snapshot(clients)
    return rollup.resolve_budget(
        rollup.total_resources(snapshot.pods), settings, snapshot.resource_quotas
    )

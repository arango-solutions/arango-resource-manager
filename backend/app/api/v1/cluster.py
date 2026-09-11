"""Cluster connection and capability reporting."""

from __future__ import annotations

from fastapi import APIRouter
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel

from app.api.deps import CapabilitiesDep, ClientsDep, SettingsDep

router = APIRouter(tags=["cluster"])


class SafetyGates(BaseModel):
    read_only: bool
    allow_guarded_actions: bool
    allow_database_scaling: bool


class ClusterInfo(BaseModel):
    namespace: str
    context: str
    config_source: str
    server_version: str | None
    capabilities: dict[str, object]
    safety: SafetyGates
    budget_mode: str


@router.get("/cluster/info", response_model=ClusterInfo)
def cluster_info(clients: ClientsDep, caps: CapabilitiesDep, settings: SettingsDep) -> ClusterInfo:
    """Report where we are connected, what we may do, and which gates are closed."""
    try:
        version = clients.version.get_code(_request_timeout=10)
        server_version = f"{version.major}.{version.minor}"
    except ApiException:
        server_version = None

    return ClusterInfo(
        namespace=clients.namespace,
        context=clients.context,
        config_source=clients.source,
        server_version=server_version,
        capabilities=caps.as_dict(),
        safety=SafetyGates(
            read_only=settings.read_only,
            allow_guarded_actions=settings.allow_guarded_actions,
            allow_database_scaling=settings.allow_database_scaling,
        ),
        budget_mode=settings.budget_mode,
    )

"""Inventory models: pods, workloads, and the services they roll up into."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.common import Protection, ResourceTriple, WorkloadRef


class Condition(BaseModel):
    type: str
    status: bool
    reason: str | None = None
    message: str | None = None


class ContainerSummary(BaseModel):
    name: str
    image: str | None = None
    ready: bool = False
    restart_count: int = 0
    started_at: str | None = None
    """When this container last started - not when the pod was admitted."""
    state: str | None = None
    last_terminated_reason: str | None = None
    resources: ResourceTriple = Field(default_factory=ResourceTriple)


class PodSummary(BaseModel):
    name: str
    phase: str
    ready: bool
    ready_containers: str
    """Rendered as "3/4"."""

    service: str | None = None
    workload: WorkloadRef | None = None
    protection: Protection = Field(default_factory=Protection)

    node: str | None = None
    start_time: str | None = None
    age_seconds: int | None = None
    ready_since_seconds: int | None = None
    restart_count: int = 0
    last_restart_at: str | None = None

    containers: list[str] = Field(default_factory=list)
    resources: ResourceTriple = Field(default_factory=ResourceTriple)


class PodDetail(PodSummary):
    labels: dict[str, str] = Field(default_factory=dict)
    container_details: list[ContainerSummary] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)


class WorkloadSummary(BaseModel):
    kind: str
    name: str
    service: str | None = None
    component: str | None = None
    """The `component` label, e.g. "api" or "worker-pdf", where one exists."""

    match_confidence: str | None = None
    protection: Protection = Field(default_factory=Protection)

    desired_replicas: int = 0
    ready_replicas: int = 0
    current_replicas: int = 0

    chart_version: str | None = None
    tier: str | None = None
    """For ArangoDeployment members: the spec field that controls the count."""

    pod_count: int = 0
    resources: ResourceTriple = Field(default_factory=ResourceTriple)


class EventSummary(BaseModel):
    type: str
    reason: str | None = None
    message: str | None = None
    count: int = 1
    last_seen: str | None = None
    involved_kind: str | None = None
    involved_name: str | None = None


class ServiceGroup(BaseModel):
    name: str
    title: str
    source: str
    """"ArangoPlatformService", "ArangoDeployment", or "unmanaged"."""
    match_confidence: str | None = None

    chart_name: str | None = None
    chart_version: str | None = None
    catalog_version: str | None = None
    version_drift: bool = False
    """True when the deployed chart version differs from the catalog's."""

    ready: bool | None = None
    conditions: list[Condition] = Field(default_factory=list)
    route_path: str | None = None

    protection: Protection = Field(default_factory=Protection)

    workload_count: int = 0
    pod_count: int = 0
    ready_pods: int = 0
    desired_replicas: int = 0
    instances: list[str] = Field(default_factory=list)

    resources: ResourceTriple = Field(default_factory=ResourceTriple)

    warning_count: int = 0
    latest_warning: str | None = None
    """Why a service is unhealthy usually lives in an event, not a condition.

    The ArangoPlatformService conditions report *which* check failed
    (ReleaseReady=False, message "Not ready"); the event carries the actual
    diagnosis ("db_name is required to install the service"). Showing only
    conditions would tell a user something is broken without telling them what.
    """


class ServiceDetail(ServiceGroup):
    workloads: list[WorkloadSummary] = Field(default_factory=list)
    pods: list[PodSummary] = Field(default_factory=list)
    events: list[EventSummary] = Field(default_factory=list)


class InventorySnapshot(BaseModel):
    namespace: str
    captured_at: str
    services: list[ServiceGroup] = Field(default_factory=list)
    workloads: list[WorkloadSummary] = Field(default_factory=list)
    pods: list[PodSummary] = Field(default_factory=list)
    service_warnings: dict[str, list[EventSummary]] = Field(default_factory=dict)
    """Recent warnings per service, capped. The group carries only a count and
    the latest message; the detail view needs the list, and re-reading events
    per request would cost another round trip."""

    degraded: list[str] = Field(default_factory=list)
    """Slices that could not be read - the UI says so rather than showing zero."""

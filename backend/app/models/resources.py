"""Capacity models: the budget ladder, rollups, and reclaimable waste."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Protection, ResourceTriple


class BudgetSource(StrEnum):
    QUOTA = "quota"
    """A ResourceQuota exists. The only source that is a real ceiling."""

    CONFIGURED = "configured"
    """Set by the operator of this tool in config."""

    DERIVED = "derived"
    """Inferred from current reservations. A starting point, not a limit."""


class Budget(BaseModel):
    cpu_cores: float | None = None
    memory_bytes: int | None = None
    source: BudgetSource = BudgetSource.DERIVED
    label: str = ""
    """Human-readable provenance, shown next to every number it produces."""

    is_policy: bool = True
    """True when this is a number someone chose rather than one the cluster
    enforces. The UI must never present a derived budget as capacity."""


class ResourceReport(BaseModel):
    """Usage, reservations and limits at one scope, with what follows from them."""

    scope: str
    name: str
    title: str | None = None
    resources: ResourceTriple

    cpu_efficiency: float | None = None
    memory_efficiency: float | None = None
    cpu_overcommit: float | None = None
    """Limits over requests. How far the namespace is oversubscribed if
    everything bursts at once."""

    reclaimable_cpu_cores: float | None = None
    reclaimable_memory_bytes: int | None = None

    pod_count: int = 0
    replicas: int = 0
    unset_limit_containers: int = 0
    unset_request_containers: int = 0


class NamespaceOverview(BaseModel):
    namespace: str
    captured_at: str
    metrics_available: bool

    totals: ResourceReport
    budget: Budget
    cpu_budget_used: float | None = None
    memory_budget_used: float | None = None

    service_count: int = 0
    services_not_ready: int = 0
    workload_count: int = 0
    deployment_count: int = 0
    statefulset_count: int = 0
    pod_count: int = 0
    ready_pods: int = 0

    pods_without_limits: int = 0
    pods_without_limits_actionable: int = 0
    """Of the above, those not owned by an operator.

    Reporting one flat count would overstate the risk: an ArangoDB cluster
    member without a CPU limit is a deliberate choice by the operator, not an
    oversight, and nothing here can change it anyway."""

    pods_with_recent_restarts: int = 0
    warning_services: list[str] = Field(default_factory=list)

    reclaimable_cost_per_day: float | None = None
    degraded: list[str] = Field(default_factory=list)


class WasteItem(BaseModel):
    """A workload reserving materially more than it uses."""

    kind: str
    name: str
    service: str | None = None
    protection: Protection = Field(default_factory=Protection)

    replicas: int = 0
    pod_count: int = 0
    resources: ResourceTriple

    cpu_efficiency: float | None = None
    memory_efficiency: float | None = None
    reclaimable_cpu_cores: float = 0.0
    reclaimable_memory_bytes: int = 0
    cost_per_day: float | None = None


class UnboundedPod(BaseModel):
    """A pod with at least one container free to consume a whole node."""

    name: str
    service: str | None = None
    workload: str | None = None
    protection: Protection = Field(default_factory=Protection)
    """Most unbounded pods here are the database, where the operator omits
    limits deliberately. Carrying the level lets the UI separate what the
    reader can act on from what they cannot."""

    unset_limit_containers: int
    container_count: int
    cpu_usage: float | None = None
    memory_usage: int | None = None

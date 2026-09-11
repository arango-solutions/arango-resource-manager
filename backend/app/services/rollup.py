"""Capacity arithmetic: the budget ladder, rollups, waste and risk.

The honest problem this module solves: there is no true capacity number
available. The credential is namespace-scoped, so node allocatable cannot be
read, and this namespace has no ResourceQuota. Inventing a capacity figure
would be the worst outcome, so the model is a four-layer ladder where three
layers are facts and only the fourth is policy:

    ACTUAL     what metrics-server measures now          fact
    REQUESTS   what the scheduler has reserved - what    fact
               the namespace holds from the cluster
               whether it uses it or not
    LIMITS     what it may burst to                      fact
    BUDGET     an allowance someone agreed               POLICY

Requests is the denominator for "provisioned": it is what the namespace has
taken out of the cluster and what nobody else can schedule onto. The budget is
labelled with its provenance everywhere it appears, so a derived number is
never mistaken for a ceiling the cluster enforces.
"""

from __future__ import annotations

import math
from typing import Any

from app.config import Settings
from app.models.common import ProtectionLevel, ResourceTriple
from app.models.inventory import InventorySnapshot, PodSummary, WorkloadSummary
from app.models.resources import (
    Budget,
    BudgetSource,
    NamespaceOverview,
    ResourceReport,
    UnboundedPod,
    WasteItem,
)
from app.services.quantities import gi_to_bytes, parse_cpu, parse_memory

_GI = 1024**3
_HOURS_PER_DAY = 24

# A workload younger than this is still settling: caches cold, first requests
# not yet served. Calling it wasteful would be wrong.
MIN_AGE_FOR_WASTE_SECONDS = 3600

# Below this, a workload is reserving far more than it will ever use.
WASTE_EFFICIENCY_CEILING = 0.6


def total_resources(pods: list[PodSummary]) -> ResourceTriple:
    total = ResourceTriple()
    for pod in pods:
        total = total + pod.resources
    return total


def _nice_ceiling(value: float) -> float:
    """Round up to a number a person would actually write down."""
    if value <= 0:
        return 0.0
    for step in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024):
        if value <= step:
            return float(step)
    return float(math.ceil(value / 256) * 256)


def resolve_budget(
    totals: ResourceTriple,
    settings: Settings,
    quotas: list[dict[str, Any]] | None = None,
) -> Budget:
    """Work out what to measure reservations against, and say where it came from."""
    quotas = quotas or []

    # 1. A ResourceQuota is the only real ceiling, so it wins whenever present.
    if settings.budget_mode in ("auto", "quota") and quotas:
        quota = quotas[0]
        hard = (quota.get("status", {}) or {}).get("hard") or (quota.get("spec", {}) or {}).get(
            "hard", {}
        )
        cpu = parse_cpu(hard.get("requests.cpu") or hard.get("limits.cpu"))
        memory = parse_memory(hard.get("requests.memory") or hard.get("limits.memory"))
        if cpu is not None or memory is not None:
            name = (quota.get("metadata", {}) or {}).get("name", "quota")
            return Budget(
                cpu_cores=cpu,
                memory_bytes=memory,
                source=BudgetSource.QUOTA,
                label=f"ResourceQuota {name}",
                is_policy=False,
            )

    # 2. An explicitly configured allowance. Setting either value is taken as
    #    intent, whatever the mode says, so a configured number is never
    #    silently ignored.
    if settings.budget_cpu_cores is not None or settings.budget_memory_gi is not None:
        return Budget(
            cpu_cores=settings.budget_cpu_cores,
            memory_bytes=gi_to_bytes(settings.budget_memory_gi),
            source=BudgetSource.CONFIGURED,
            label="configured",
        )

    # 3. Derived from what is already reserved, plus headroom. Explicitly a
    #    starting point for a conversation, not a capacity reading.
    reserved_cpu = totals.requests.cpu_cores
    reserved_memory = totals.requests.memory_bytes
    factor = settings.budget_headroom_factor

    return Budget(
        cpu_cores=_nice_ceiling(reserved_cpu * factor) if reserved_cpu else None,
        memory_bytes=(
            int(_nice_ceiling(reserved_memory * factor / _GI) * _GI) if reserved_memory else None
        ),
        source=BudgetSource.DERIVED,
        label="derived — set a budget in Settings",
    )


def _report(
    scope: str,
    name: str,
    resources: ResourceTriple,
    *,
    title: str | None = None,
    pod_count: int = 0,
    replicas: int = 0,
) -> ResourceReport:
    requests_cpu = resources.requests.cpu_cores
    limits_cpu = resources.limits.cpu_cores
    return ResourceReport(
        scope=scope,
        name=name,
        title=title,
        resources=resources,
        cpu_efficiency=resources.cpu_efficiency,
        memory_efficiency=resources.memory_efficiency,
        cpu_overcommit=(
            limits_cpu / requests_cpu if requests_cpu and limits_cpu is not None else None
        ),
        reclaimable_cpu_cores=resources.reclaimable_cpu_cores,
        reclaimable_memory_bytes=resources.reclaimable_memory_bytes,
        pod_count=pod_count,
        replicas=replicas,
        unset_limit_containers=resources.unset_limit_containers,
        unset_request_containers=resources.unset_request_containers,
    )


def namespace_report(snapshot: InventorySnapshot) -> ResourceReport:
    return _report(
        "namespace",
        snapshot.namespace,
        total_resources(snapshot.pods),
        pod_count=len(snapshot.pods),
    )


def service_reports(snapshot: InventorySnapshot) -> list[ResourceReport]:
    return [
        _report(
            "service",
            service.name,
            service.resources,
            title=service.title,
            pod_count=service.pod_count,
            replicas=service.desired_replicas,
        )
        for service in snapshot.services
    ]


def workload_reports(snapshot: InventorySnapshot) -> list[ResourceReport]:
    return [
        _report(
            "workload",
            workload.name,
            workload.resources,
            title=workload.service,
            pod_count=workload.pod_count,
            replicas=workload.desired_replicas,
        )
        for workload in snapshot.workloads
    ]


def _oldest_pod_age(snapshot: InventorySnapshot, workload: WorkloadSummary) -> int:
    ages = [
        pod.age_seconds or 0
        for pod in snapshot.pods
        if pod.workload and pod.workload.name == workload.name
    ]
    return max(ages, default=0)


def waste(snapshot: InventorySnapshot, settings: Settings, limit: int = 20) -> list[WasteItem]:
    """Workloads reserving materially more than they use, worst first.

    Protected workloads are excluded: this tool will not act on them, so
    ranking them would be pointing at something the reader cannot fix.
    """
    items: list[WasteItem] = []

    for workload in snapshot.workloads:
        if workload.protection.level is ProtectionLevel.PROTECTED:
            continue
        if _oldest_pod_age(snapshot, workload) < MIN_AGE_FOR_WASTE_SECONDS:
            continue

        resources = workload.resources
        reclaimable_cpu = resources.reclaimable_cpu_cores
        reclaimable_memory = resources.reclaimable_memory_bytes
        if reclaimable_cpu is None and reclaimable_memory is None:
            continue

        efficiency = resources.cpu_efficiency
        if efficiency is not None and efficiency >= WASTE_EFFICIENCY_CEILING:
            continue

        items.append(
            WasteItem(
                kind=workload.kind,
                name=workload.name,
                service=workload.service,
                protection=workload.protection,
                replicas=workload.desired_replicas,
                pod_count=workload.pod_count,
                resources=resources,
                cpu_efficiency=efficiency,
                memory_efficiency=resources.memory_efficiency,
                reclaimable_cpu_cores=reclaimable_cpu or 0.0,
                reclaimable_memory_bytes=reclaimable_memory or 0,
                cost_per_day=_cost_per_day(
                    reclaimable_cpu or 0.0, reclaimable_memory or 0, settings
                ),
            )
        )

    items.sort(
        key=lambda item: (item.reclaimable_cpu_cores, item.reclaimable_memory_bytes),
        reverse=True,
    )
    return items[:limit]


def unbounded_pods(snapshot: InventorySnapshot) -> list[UnboundedPod]:
    """Pods with a container that has no limit, and so no ceiling at all."""
    return [
        UnboundedPod(
            name=pod.name,
            service=pod.service,
            workload=pod.workload.name if pod.workload else None,
            protection=pod.protection,
            unset_limit_containers=pod.resources.unset_limit_containers,
            container_count=pod.resources.container_count,
            cpu_usage=pod.resources.usage.cpu_cores,
            memory_usage=pod.resources.usage.memory_bytes,
        )
        for pod in snapshot.pods
        if pod.resources.unset_limit_containers > 0
    ]


def _cost_per_day(cpu_cores: float, memory_bytes: int, settings: Settings) -> float | None:
    """Only ever a real number when rates are configured - never an invented price."""
    if not settings.cost_per_core_hour and not settings.cost_per_gi_hour:
        return None
    return (
        cpu_cores * settings.cost_per_core_hour + (memory_bytes / _GI) * settings.cost_per_gi_hour
    ) * _HOURS_PER_DAY


def overview(
    snapshot: InventorySnapshot,
    settings: Settings,
    quotas: list[dict[str, Any]] | None = None,
    metrics_available: bool = True,
) -> NamespaceOverview:
    totals = namespace_report(snapshot)
    budget = resolve_budget(totals.resources, settings, quotas)

    reserved_cpu = totals.resources.requests.cpu_cores
    reserved_memory = totals.resources.requests.memory_bytes

    unbounded = unbounded_pods(snapshot)
    restarted = [p for p in snapshot.pods if p.restart_count > 0]

    return NamespaceOverview(
        namespace=snapshot.namespace,
        captured_at=snapshot.captured_at,
        metrics_available=metrics_available,
        totals=totals,
        budget=budget,
        cpu_budget_used=(
            reserved_cpu / budget.cpu_cores if reserved_cpu and budget.cpu_cores else None
        ),
        memory_budget_used=(
            reserved_memory / budget.memory_bytes
            if reserved_memory and budget.memory_bytes
            else None
        ),
        service_count=len(snapshot.services),
        services_not_ready=sum(1 for s in snapshot.services if s.ready is False),
        workload_count=len(snapshot.workloads),
        deployment_count=sum(1 for w in snapshot.workloads if w.kind == "Deployment"),
        statefulset_count=sum(1 for w in snapshot.workloads if w.kind == "StatefulSet"),
        pod_count=len(snapshot.pods),
        ready_pods=sum(1 for p in snapshot.pods if p.ready),
        pods_without_limits=len(unbounded),
        pods_without_limits_actionable=sum(
            1 for p in unbounded if p.protection.level is not ProtectionLevel.PROTECTED
        ),
        pods_with_recent_restarts=len(restarted),
        warning_services=[s.name for s in snapshot.services if s.warning_count > 0],
        reclaimable_cost_per_day=_cost_per_day(
            totals.reclaimable_cpu_cores or 0.0,
            totals.reclaimable_memory_bytes or 0,
            settings,
        ),
        degraded=snapshot.degraded,
    )

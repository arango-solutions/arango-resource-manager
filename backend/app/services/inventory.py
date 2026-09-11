"""Builds the single snapshot every read route serves from.

One pass over the namespace produces pods, workloads and services together, so
every number on a page comes from the same moment rather than from several
independent reads that disagree with each other.

A slice that cannot be read degrades to empty and is named in `degraded`. The
UI says "this could not be read" instead of quietly showing zero, because a
zero here would look exactly like a healthy empty namespace.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import structlog
from kubernetes.client.exceptions import ApiException

from app.config import Settings, get_settings
from app.k8s.client import ARANGO_CRS, KubeClients, get_clients
from app.models.common import Protection, ProtectionLevel, Resources, ResourceTriple, WorkloadRef
from app.models.inventory import (
    Condition,
    ContainerSummary,
    EventSummary,
    InventorySnapshot,
    PodDetail,
    PodSummary,
    ServiceDetail,
    ServiceGroup,
    WorkloadSummary,
)
from app.services.cache import TTLCache
from app.services.grouping import (
    ARANGO_CLUSTER_KEY,
    ARANGO_CLUSTER_TITLE,
    ROLE_TO_TIER,
    build_pod_index,
    chart_index,
    chart_version,
    component_of,
    conditions_of,
    labels_of,
    name_of,
    resolve_services,
    route_index,
)
from app.services.protection import classify_pod, classify_workload, strictest
from app.services.quantities import parse_cpu, parse_memory

log = structlog.get_logger(__name__)

_TIMEOUT = 30

# The detail view shows a handful; keeping every one of several hundred
# duplicated install failures in the snapshot would bloat it for no gain.
_MAX_WARNINGS_PER_SERVICE = 20


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _age_seconds(value: Any, now: datetime) -> int | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def container_resources(container: dict[str, Any]) -> ResourceTriple:
    """Requests and limits for one container. Usage is filled in by the metrics layer."""
    resources = container.get("resources") or {}
    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    request_block = Resources(
        cpu_cores=parse_cpu(requests.get("cpu")),
        memory_bytes=parse_memory(requests.get("memory")),
    )
    limit_block = Resources(
        cpu_cores=parse_cpu(limits.get("cpu")),
        memory_bytes=parse_memory(limits.get("memory")),
    )
    return ResourceTriple(
        requests=request_block,
        limits=limit_block,
        unset_request_containers=0 if request_block.is_set else 1,
        unset_limit_containers=0 if limit_block.is_set else 1,
        container_count=1,
    )


def _pod_resources(pod: dict[str, Any]) -> ResourceTriple:
    total = ResourceTriple()
    for container in pod.get("spec", {}).get("containers", []) or []:
        total = total + container_resources(container)
    return total


def _container_statuses(pod: dict[str, Any]) -> list[dict[str, Any]]:
    return list((pod.get("status", {}) or {}).get("containerStatuses") or [])


def _ready_condition_time(pod: dict[str, Any]) -> Any:
    for condition in (pod.get("status", {}) or {}).get("conditions") or []:
        if condition.get("type") == "Ready" and str(condition.get("status")).lower() == "true":
            return condition.get("lastTransitionTime")
    return None


def build_pod_summary(
    pod: dict[str, Any],
    now: datetime,
    settings: Settings,
    service: str | None = None,
    workload: WorkloadRef | None = None,
) -> PodSummary:
    metadata = pod.get("metadata", {})
    status = pod.get("status", {}) or {}
    statuses = _container_statuses(pod)

    ready_count = sum(1 for c in statuses if c.get("ready"))
    total_containers = len(pod.get("spec", {}).get("containers", []) or [])

    restarts = sum(int(c.get("restartCount") or 0) for c in statuses)
    last_restart = max(
        (
            _iso(((c.get("lastState") or {}).get("terminated") or {}).get("finishedAt"))
            for c in statuses
        ),
        default=None,
        key=lambda value: value or "",
    )

    return PodSummary(
        name=name_of(pod),
        phase=str(status.get("phase", "Unknown")),
        ready=ready_count == total_containers and total_containers > 0,
        ready_containers=f"{ready_count}/{total_containers}",
        service=service,
        workload=workload,
        protection=classify_pod(pod, settings),
        node=pod.get("spec", {}).get("nodeName"),
        start_time=_iso(status.get("startTime")),
        age_seconds=_age_seconds(status.get("startTime") or metadata.get("creationTimestamp"), now),
        ready_since_seconds=_age_seconds(_ready_condition_time(pod), now),
        restart_count=restarts,
        last_restart_at=last_restart or None,
        containers=[
            str(c.get("name", "")) for c in pod.get("spec", {}).get("containers", []) or []
        ],
        resources=_pod_resources(pod),
    )


def build_pod_detail(pod: dict[str, Any], summary: PodSummary) -> PodDetail:
    spec_containers = {
        str(c.get("name", "")): c for c in pod.get("spec", {}).get("containers", []) or []
    }
    details: list[ContainerSummary] = []

    for status in _container_statuses(pod):
        name = str(status.get("name", ""))
        state = status.get("state") or {}
        running = state.get("running") or {}
        state_name = next(iter(state), None)
        terminated = (status.get("lastState") or {}).get("terminated") or {}
        spec = spec_containers.get(name, {})

        details.append(
            ContainerSummary(
                name=name,
                image=status.get("image"),
                ready=bool(status.get("ready")),
                restart_count=int(status.get("restartCount") or 0),
                # The container's own start time. A crash-looping pod is old
                # while its container is minutes young; conflating the two hides
                # exactly the problem the user is looking for.
                started_at=_iso(running.get("startedAt")),
                state=str(state_name) if state_name else None,
                last_terminated_reason=terminated.get("reason"),
                resources=container_resources(spec) if spec else ResourceTriple(),
            )
        )

    conditions = [
        Condition(
            type=str(c.get("type", "")),
            status=str(c.get("status", "")).lower() == "true",
            reason=c.get("reason"),
            message=c.get("message"),
        )
        for c in (pod.get("status", {}) or {}).get("conditions") or []
    ]

    return PodDetail(
        **summary.model_dump(),
        labels=labels_of(pod),
        container_details=details,
        conditions=conditions,
    )


def _fetch(clients: KubeClients, degraded: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Read every slice, degrading each independently.

    The slices are fetched concurrently. Each call is a round trip to an API
    server that may be a long way away - measured at ~900ms each against a
    cluster in another region - so running the eight of them in sequence costs
    several seconds on every cold snapshot. They do not depend on one another,
    so a small thread pool turns that into roughly one round trip. The
    Kubernetes client's underlying urllib3 pool is thread-safe for the reads
    done here; nothing in this function mutates shared client state.
    """
    namespace = clients.namespace
    api = clients.core.api_client

    def core_list(call: Any) -> list[dict[str, Any]]:
        return list(api.sanitize_for_serialization(call())["items"])

    def cr_list(kind: str) -> list[dict[str, Any]]:
        group, version, plural = ARANGO_CRS[kind]
        response = clients.custom.list_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            _request_timeout=_TIMEOUT,
        )
        return list(response.get("items", []))

    loaders: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "pods": lambda: core_list(
            lambda: clients.core.list_namespaced_pod(namespace, _request_timeout=_TIMEOUT)
        ),
        "deployments": lambda: core_list(
            lambda: clients.apps.list_namespaced_deployment(namespace, _request_timeout=_TIMEOUT)
        ),
        "statefulsets": lambda: core_list(
            lambda: clients.apps.list_namespaced_stateful_set(namespace, _request_timeout=_TIMEOUT)
        ),
        "replicasets": lambda: core_list(
            lambda: clients.apps.list_namespaced_replica_set(namespace, _request_timeout=_TIMEOUT)
        ),
        "events": lambda: core_list(
            lambda: clients.core.list_namespaced_event(namespace, _request_timeout=_TIMEOUT)
        ),
        "platform_services": lambda: cr_list("ArangoPlatformService"),
        "charts": lambda: cr_list("ArangoPlatformChart"),
        "routes": lambda: cr_list("ArangoRoute"),
        "arango_deployments": lambda: cr_list("ArangoDeployment"),
    }

    results: dict[str, list[dict[str, Any]]] = {}
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=len(loaders), thread_name_prefix="inventory") as pool:
        futures = {pool.submit(loader): label for label, loader in loaders.items()}
        for future in as_completed(futures):
            label = futures[future]
            try:
                results[label] = future.result()
            except (ApiException, KeyError, TypeError) as exc:
                # One unreadable slice degrades that slice only. Returning empty
                # here would be indistinguishable from a healthy empty namespace,
                # so the name is recorded and the UI says it could not be read.
                log.warning("inventory.slice.failed", slice=label, error=str(exc))
                degraded.append(label)
                results[label] = []

    log.info(
        "inventory.fetched",
        ms=round((time.monotonic() - started) * 1000),
        degraded=degraded or None,
    )
    return results


def assemble(
    raw: dict[str, list[dict[str, Any]]],
    namespace: str,
    settings: Settings,
    now: datetime | None = None,
    degraded: list[str] | None = None,
) -> InventorySnapshot:
    """Turn raw API objects into the snapshot. Pure: no cluster access."""
    now = now or datetime.now(UTC)
    protected_kinds = set(settings.protected_owner_kind_list)

    pods = raw.get("pods", [])
    # Carry the kind alongside each object; comparing dicts to work out which
    # list an object came from is both slow and quietly wrong on equal specs.
    kinded: list[tuple[str, dict[str, Any]]] = [
        ("Deployment", obj) for obj in raw.get("deployments", [])
    ] + [("StatefulSet", obj) for obj in raw.get("statefulsets", [])]
    workload_objects = [obj for _, obj in kinded]
    platform_services = raw.get("platform_services", [])

    pod_index, standalone = build_pod_index(pods, raw.get("replicasets", []), protected_kinds)
    service_of = resolve_services(workload_objects, platform_services)
    routes = route_index(raw.get("routes", []))
    catalog = chart_index(raw.get("charts", []))
    warnings = _warning_index(raw.get("events", []))

    workloads: list[WorkloadSummary] = []
    pod_summaries: list[PodSummary] = []

    # --- Deployments and StatefulSets -----------------------------------
    for kind, obj in kinded:
        workload_name = name_of(obj)
        service, confidence = service_of.get(workload_name, (workload_name, "unmanaged"))
        members = pod_index.get((kind, workload_name), [])
        status = obj.get("status", {}) or {}

        protection = classify_workload(workload_name, members, settings)
        resources = ResourceTriple()
        ref = WorkloadRef(kind=kind, name=workload_name)

        for pod in members:
            summary = build_pod_summary(pod, now, settings, service=service, workload=ref)
            pod_summaries.append(summary)
            resources = resources + summary.resources

        workloads.append(
            WorkloadSummary(
                kind=kind,
                name=workload_name,
                service=service,
                component=component_of(obj),
                match_confidence=confidence,
                protection=protection,
                desired_replicas=int(obj.get("spec", {}).get("replicas") or 0),
                ready_replicas=int(status.get("readyReplicas") or 0),
                current_replicas=int(status.get("replicas") or 0),
                chart_version=chart_version(obj),
                pod_count=len(members),
                resources=resources,
            )
        )

    # --- ArangoDB cluster members, grouped by role -----------------------
    arango_spec = (raw.get("arango_deployments") or [{}])[0].get("spec", {}) or {}
    for (kind, role), members in sorted(pod_index.items()):
        if kind not in protected_kinds:
            continue
        tier = ROLE_TO_TIER.get(role, role)
        desired = int((arango_spec.get(tier) or {}).get("count") or len(members))
        ref = WorkloadRef(kind=kind, name=role)
        resources = ResourceTriple()

        for pod in members:
            summary = build_pod_summary(
                pod, now, settings, service=ARANGO_CLUSTER_KEY, workload=ref
            )
            pod_summaries.append(summary)
            resources = resources + summary.resources

        workloads.append(
            WorkloadSummary(
                kind=kind,
                name=role,
                service=ARANGO_CLUSTER_KEY,
                component=role,
                match_confidence="owner",
                protection=classify_workload(role, members, settings),
                desired_replicas=desired,
                ready_replicas=sum(1 for p in members if _is_ready(p)),
                current_replicas=len(members),
                tier=tier,
                pod_count=len(members),
                resources=resources,
            )
        )

    # --- Pods with no controller ----------------------------------------
    for pod in standalone:
        pod_summaries.append(build_pod_summary(pod, now, settings, service=None, workload=None))

    services, service_warnings = _assemble_services(
        workloads, pod_summaries, platform_services, routes, catalog, service_of, warnings
    )

    return InventorySnapshot(
        namespace=namespace,
        captured_at=now.isoformat(),
        services=sorted(services, key=lambda s: s.name),
        workloads=sorted(workloads, key=lambda w: (w.service or "", w.name)),
        pods=sorted(pod_summaries, key=lambda p: p.name),
        service_warnings=service_warnings,
        degraded=degraded or [],
    )


def _is_ready(pod: dict[str, Any]) -> bool:
    statuses = _container_statuses(pod)
    return bool(statuses) and all(c.get("ready") for c in statuses)


def _assemble_services(
    workloads: list[WorkloadSummary],
    pods: list[PodSummary],
    platform_services: list[dict[str, Any]],
    routes: dict[str, str],
    catalog: dict[str, str],
    service_of: dict[str, tuple[str, str]],
    warnings: dict[str, list[EventSummary]],
) -> tuple[list[ServiceGroup], dict[str, list[EventSummary]]]:
    by_service: dict[str, list[WorkloadSummary]] = {}
    for workload in workloads:
        by_service.setdefault(workload.service or "", []).append(workload)

    pods_by_service: dict[str, list[PodSummary]] = {}
    for pod in pods:
        pods_by_service.setdefault(pod.service or "", []).append(pod)

    declared = {name_of(svc): svc for svc in platform_services}
    groups: list[ServiceGroup] = []
    per_service: dict[str, list[EventSummary]] = {}

    # A declared service with no workloads still gets a group: that is exactly
    # the state of a service whose Helm install is failing, and hiding it would
    # hide the problem.
    for key in sorted(set(by_service) | set(declared)):
        if not key:
            continue
        members = by_service.get(key, [])
        member_pods = pods_by_service.get(key, [])
        declaration = declared.get(key)

        resources = ResourceTriple()
        for workload in members:
            resources = resources + workload.resources

        chart_name: str | None = None
        conditions: list[Condition] = []
        ready: bool | None = None
        source = "unmanaged"

        if key == ARANGO_CLUSTER_KEY:
            source = "ArangoDeployment"
        elif declaration is not None:
            source = "ArangoPlatformService"
            chart_name = (declaration.get("spec", {}).get("chart") or {}).get("name")
            conditions = [Condition(**c) for c in conditions_of(declaration)]
            ready = _service_ready(conditions)

        deployed_version = next((w.chart_version for w in members if w.chart_version), None)
        catalog_version = catalog.get(chart_name or key)

        # Warnings are collected against the service itself, its workloads and
        # its pods, so a failure anywhere in the group surfaces on the card.
        related = {key, *(w.name for w in members), *(p.name for p in member_pods)}
        group_warnings = [event for name in related for event in warnings.get(name, [])]
        group_warnings.sort(key=lambda e: e.last_seen or "", reverse=True)
        if group_warnings:
            per_service[key] = group_warnings[:_MAX_WARNINGS_PER_SERVICE]

        groups.append(
            ServiceGroup(
                name=key,
                title=ARANGO_CLUSTER_TITLE if key == ARANGO_CLUSTER_KEY else key,
                source=source,
                match_confidence=next((w.match_confidence for w in members), None),
                chart_name=chart_name,
                chart_version=deployed_version,
                catalog_version=catalog_version,
                version_drift=bool(
                    deployed_version and catalog_version and deployed_version != catalog_version
                ),
                ready=ready if ready is not None else _pods_ready(member_pods),
                conditions=conditions,
                route_path=routes.get(key) or _route_for_instances(routes, members, service_of),
                protection=_group_protection(members),
                workload_count=len(members),
                pod_count=len(member_pods),
                ready_pods=sum(1 for p in member_pods if p.ready),
                desired_replicas=sum(w.desired_replicas for w in members),
                instances=sorted({w.name for w in members}),
                resources=resources,
                warning_count=sum(e.count for e in group_warnings),
                latest_warning=group_warnings[0].message if group_warnings else None,
            )
        )

    return groups, per_service


def _warning_index(events: list[dict[str, Any]]) -> dict[str, list[EventSummary]]:
    """Group Warning events by the name of the object they concern.

    Identical warnings are collapsed into one entry with their counts summed.
    A failing Helm install repeats the same message hundreds of times; showing
    it hundreds of times buries every *other* warning and tells the reader
    nothing the count does not already say.
    """
    index: dict[str, dict[tuple[str, str], EventSummary]] = {}

    for event in events:
        if event.get("type") != "Warning":
            continue
        involved = event.get("involvedObject") or {}
        name = str(involved.get("name", ""))
        if not name:
            continue

        reason = str(event.get("reason") or "")
        message = str(event.get("message") or "")
        count = int(event.get("count") or 1)
        last_seen = _iso(event.get("lastTimestamp") or event.get("eventTime"))

        bucket = index.setdefault(name, {})
        existing = bucket.get((reason, message))
        if existing is None:
            bucket[(reason, message)] = EventSummary(
                type="Warning",
                reason=event.get("reason"),
                message=event.get("message"),
                count=count,
                last_seen=last_seen,
                involved_kind=involved.get("kind"),
                involved_name=name,
            )
        else:
            existing.count += count
            if (last_seen or "") > (existing.last_seen or ""):
                existing.last_seen = last_seen

    return {name: list(bucket.values()) for name, bucket in index.items()}


def _service_ready(conditions: list[Condition]) -> bool | None:
    if not conditions:
        return None
    return all(c.status for c in conditions)


def _pods_ready(pods: list[PodSummary]) -> bool | None:
    if not pods:
        return None
    return all(p.ready for p in pods)


def _route_for_instances(
    routes: dict[str, str],
    members: list[WorkloadSummary],
    _service_of: dict[str, tuple[str, str]],
) -> str | None:
    """Satellite releases carry their own route, named after the instance."""
    for workload in members:
        path = routes.get(workload.name)
        if path:
            return path
    return None


def _group_protection(members: list[WorkloadSummary]) -> Protection:
    if not members:
        return Protection(level=ProtectionLevel.NORMAL)
    return strictest([w.protection for w in members])


_cache: TTLCache[InventorySnapshot] = TTLCache(get_settings().inventory_ttl_seconds)


def get_snapshot(clients: KubeClients | None = None) -> InventorySnapshot:
    """The cached namespace snapshot every read route serves from."""

    def load() -> InventorySnapshot:
        active = clients or get_clients()
        settings = get_settings()
        degraded: list[str] = []
        raw = _fetch(active, degraded)
        return assemble(raw, active.namespace, settings, degraded=degraded)

    return _cache.get(load)


def invalidate() -> None:
    """Drop the snapshot so the next read reflects a mutation immediately."""
    _cache.invalidate()


def get_pod_detail(clients: KubeClients, pod_name: str) -> PodDetail | None:
    """Fetch one pod in full.

    Read straight from the API rather than from the snapshot: the detail view
    needs per-container state that the summary deliberately drops, and it is a
    single-object GET rather than a list.
    """
    summary = next(
        (p for p in get_snapshot(clients).pods if p.name == pod_name),
        None,
    )
    if summary is None:
        return None
    try:
        raw = clients.core.api_client.sanitize_for_serialization(
            clients.core.read_namespaced_pod(pod_name, clients.namespace, _request_timeout=_TIMEOUT)
        )
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return build_pod_detail(raw, summary)


def build_detail(snapshot: InventorySnapshot, service_name: str) -> ServiceDetail | None:
    group = next((s for s in snapshot.services if s.name == service_name), None)
    if group is None:
        return None
    return ServiceDetail(
        **group.model_dump(),
        workloads=[w for w in snapshot.workloads if w.service == service_name],
        pods=[p for p in snapshot.pods if p.service == service_name],
        events=snapshot.service_warnings.get(service_name, []),
    )

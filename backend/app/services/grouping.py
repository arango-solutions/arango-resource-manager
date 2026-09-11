"""Rolls raw Kubernetes objects up into the services a user thinks in.

The hierarchy, from the live cluster:

    ArangoPlatformChart   the catalog of installable charts
    ArangoPlatformService what is actually deployed        <- what we group by
    Deployment/StatefulSet -> ReplicaSet -> Pod            <- what actually runs

Deployments carry an `app.kubernetes.io/instance` label that usually matches an
ArangoPlatformService name. Usually. Three things break a naive match, and the
ordered resolver below exists for them:

1. A prefix collision. Both `arangodb-platform-ui` and
   `arangodb-platform-ui-server` are services, so prefix matching lets the
   shorter one steal the longer one's deployment. Exact matches are therefore
   claimed first, and only then the LONGEST remaining prefix.
2. Satellite releases. `arangodb-graphrag-retriever-icnn5` and friends are
   separate Helm releases of one chart; they belong under the retriever service.
3. Workloads with no service at all (the operator, `arangodb-autograph-*`), and
   a service with no workloads at all (the retriever, whose install is failing).
   Both are real states and both must survive the grouping.
"""

from __future__ import annotations

from typing import Any

INSTANCE_LABEL = "app.kubernetes.io/instance"
NAME_LABEL = "app.kubernetes.io/name"
CHART_LABEL = "helm.sh/chart"
COMPONENT_LABEL = "component"

# The ArangoDB cluster members are grouped under one synthetic service rather
# than appearing as a dozen unexplained pods.
ARANGO_CLUSTER_KEY = "arangodb-cluster"
ARANGO_CLUSTER_TITLE = "ArangoDB cluster"
ROLE_LABEL = "role"

# Tier name in the ArangoDeployment spec, keyed by the pods' `role` label.
ROLE_TO_TIER = {
    "agent": "agents",
    "dbserver": "dbservers",
    "coordinator": "coordinators",
    "gateways": "gateways",
    "gateway": "gateways",
    "single": "single",
    "syncmaster": "syncmasters",
    "syncworker": "syncworkers",
}


def labels_of(obj: dict[str, Any]) -> dict[str, str]:
    return obj.get("metadata", {}).get("labels") or {}


def name_of(obj: dict[str, Any]) -> str:
    return str(obj.get("metadata", {}).get("name", ""))


def owner_refs(obj: dict[str, Any]) -> list[dict[str, Any]]:
    return list(obj.get("metadata", {}).get("ownerReferences") or [])


def build_pod_index(
    pods: list[dict[str, Any]],
    replicasets: list[dict[str, Any]],
    protected_kinds: set[str],
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    """Map each pod onto its controlling workload.

    Returns ((kind, name) -> pods, standalone pods). ReplicaSets are resolved
    through their own ownerReferences rather than by stripping the hash off the
    pod name, which is guesswork that breaks on any name containing a dash.
    """
    rs_owner: dict[str, tuple[str, str]] = {}
    for rs in replicasets:
        for ref in owner_refs(rs):
            if ref.get("kind") == "Deployment":
                rs_owner[name_of(rs)] = ("Deployment", str(ref.get("name", "")))
                break

    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    standalone: list[dict[str, Any]] = []

    for pod in pods:
        refs = owner_refs(pod)
        if not refs:
            standalone.append(pod)
            continue

        ref = refs[0]
        kind = str(ref.get("kind", ""))
        ref_name = str(ref.get("name", ""))

        if kind == "ReplicaSet":
            owner = rs_owner.get(ref_name)
            key = owner if owner else ("ReplicaSet", ref_name)
        elif kind in protected_kinds:
            # An operator-owned pod. Grouped by its role, not by a workload,
            # because there is no Deployment or StatefulSet behind it.
            role = labels_of(pod).get(ROLE_LABEL, "member")
            key = (kind, role)
        else:
            key = (kind, ref_name)

        index.setdefault(key, []).append(pod)

    return index, standalone


def resolve_services(
    workloads: list[dict[str, Any]],
    platform_services: list[dict[str, Any]],
) -> dict[str, tuple[str, str]]:
    """Map each workload name onto (service key, match confidence).

    Ordered: exact matches claim their service first, so a longest-prefix match
    can never take a service that a different workload matched exactly.
    """
    service_names = [name_of(svc) for svc in platform_services]
    chart_to_service: dict[str, str] = {}
    for svc in platform_services:
        chart = (svc.get("spec", {}).get("chart") or {}).get("name")
        if chart:
            chart_to_service.setdefault(str(chart), name_of(svc))

    resolved: dict[str, tuple[str, str]] = {}
    claimed_exactly: set[str] = set()

    # Pass A - exact instance match.
    for workload in workloads:
        instance = labels_of(workload).get(INSTANCE_LABEL)
        if instance and instance in service_names:
            resolved[name_of(workload)] = (instance, "exact")
            claimed_exactly.add(instance)

    # Pass B - longest prefix among services not claimed exactly.
    available = [svc for svc in service_names if svc not in claimed_exactly]
    for workload in workloads:
        workload_name = name_of(workload)
        if workload_name in resolved:
            continue
        instance = labels_of(workload).get(INSTANCE_LABEL)
        if not instance:
            continue
        candidates = [svc for svc in available if instance == svc or instance.startswith(f"{svc}-")]
        if candidates:
            resolved[workload_name] = (max(candidates, key=len), "instance")

    # Pass C - fall back to the chart name.
    for workload in workloads:
        workload_name = name_of(workload)
        if workload_name in resolved:
            continue
        chart_name = labels_of(workload).get(NAME_LABEL)
        if chart_name and chart_name in chart_to_service:
            resolved[workload_name] = (chart_to_service[chart_name], "chart")

    # Pass D - unmanaged: key by the instance label, or by the workload name.
    for workload in workloads:
        workload_name = name_of(workload)
        if workload_name in resolved:
            continue
        instance = labels_of(workload).get(INSTANCE_LABEL) or workload_name
        resolved[workload_name] = (instance, "unmanaged")

    return resolved


def chart_version(workload: dict[str, Any]) -> str | None:
    """Read the deployed chart version off the helm.sh/chart label.

    The label is "<chart-name>-<version>", and chart names contain dashes, so
    the version is recovered by stripping the known name rather than splitting.
    """
    chart = labels_of(workload).get(CHART_LABEL)
    if not chart:
        return None
    chart_name = labels_of(workload).get(NAME_LABEL)
    if chart_name and chart.startswith(f"{chart_name}-"):
        return chart[len(chart_name) + 1 :]
    _, _, tail = chart.rpartition("-")
    return tail or None


def component_of(workload: dict[str, Any]) -> str | None:
    return labels_of(workload).get(COMPONENT_LABEL)


def route_index(routes: list[dict[str, Any]]) -> dict[str, str]:
    """Map an ArangoRoute's target name onto its public path."""
    index: dict[str, str] = {}
    for route in routes:
        path = (route.get("spec", {}).get("route") or {}).get("path")
        if path:
            index.setdefault(name_of(route), str(path))
    return index


def chart_index(charts: list[dict[str, Any]]) -> dict[str, str]:
    """Map a chart name onto the version the catalog offers."""
    index: dict[str, str] = {}
    for chart in charts:
        status = chart.get("status", {}) or {}
        info = status.get("info") or {}
        version = info.get("version") or (chart.get("spec", {}) or {}).get("version")
        if version:
            index[name_of(chart)] = str(version)
    return index


def conditions_of(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Status conditions, normalised to booleans with their messages kept.

    The message is the point: a service showing ReleaseReady=False is far less
    useful than one showing "db_name is required to install the service".
    """
    raw = (obj.get("status", {}) or {}).get("conditions") or []
    return [
        {
            "type": str(cond.get("type", "")),
            "status": str(cond.get("status", "")).lower() == "true",
            "reason": cond.get("reason"),
            "message": cond.get("message"),
        }
        for cond in raw
    ]

"""Kubernetes client wiring: config loading, namespace resolution, capability probing."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from app.config import Settings, get_settings
from app.k8s.errors import K8sConfigError

log = structlog.get_logger(__name__)

SA_NAMESPACE_FILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")

METRICS_GROUP = "metrics.k8s.io"
METRICS_VERSION = "v1beta1"

# Arango custom resources this app reads, as (group, version, plural).
ARANGO_CRS: dict[str, tuple[str, str, str]] = {
    "ArangoPlatformService": ("platform.arangodb.com", "v1beta1", "arangoplatformservices"),
    "ArangoPlatformChart": ("platform.arangodb.com", "v1beta1", "arangoplatformcharts"),
    "ArangoRoute": ("networking.arangodb.com", "v1beta1", "arangoroutes"),
    "ArangoDeployment": ("database.arangodb.com", "v1", "arangodeployments"),
}

# Access reviews run at startup: label -> (group, resource, verb, subresource)
_ACCESS_CHECKS: dict[str, tuple[str, str, str, str]] = {
    "pods_list": ("", "pods", "list", ""),
    "pods_delete": ("", "pods", "delete", ""),
    "pods_log": ("", "pods", "get", "log"),
    "deployments_list": ("apps", "deployments", "list", ""),
    "deployments_patch": ("apps", "deployments", "patch", ""),
    "deployments_scale": ("apps", "deployments", "update", "scale"),
    "statefulsets_list": ("apps", "statefulsets", "list", ""),
    "statefulsets_scale": ("apps", "statefulsets", "update", "scale"),
    "replicasets_list": ("apps", "replicasets", "list", ""),
    "events_list": ("", "events", "list", ""),
    "resourcequotas_list": ("", "resourcequotas", "list", ""),
    "pvc_list": ("", "persistentvolumeclaims", "list", ""),
    "arangodeployments_patch": ("database.arangodb.com", "arangodeployments", "patch", ""),
    "nodes_list": ("", "nodes", "list", ""),
}


@dataclass
class Capabilities:
    """What this credential can actually do, probed once at startup."""

    access: dict[str, bool] = field(default_factory=dict)
    metrics_server: bool = False
    resourcequota_present: bool = False
    limitrange_present: bool = False
    arango_crs: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)

    def can(self, name: str) -> bool:
        return self.access.get(name, False)

    def as_dict(self) -> dict[str, object]:
        return {
            **self.access,
            "metrics_server": self.metrics_server,
            "resourcequota_present": self.resourcequota_present,
            "limitrange_present": self.limitrange_present,
            "arango_crs": self.arango_crs,
            "degraded": self.degraded,
        }


@dataclass
class KubeClients:
    """Handles onto the Kubernetes APIs, plus the resolved connection context."""

    core: client.CoreV1Api
    apps: client.AppsV1Api
    custom: client.CustomObjectsApi
    auth: client.AuthorizationV1Api
    version: client.VersionApi
    namespace: str
    context: str
    source: str  # which config path won: explicit-kubeconfig | in-cluster | default-kubeconfig


def _in_cluster() -> bool:
    return "KUBERNETES_SERVICE_HOST" in os.environ


def _load_config(settings: Settings) -> tuple[str, str]:
    """Load cluster config. Returns (source, context_name). Raises K8sConfigError."""
    ctx = settings.kube_context or None
    attempts: list[str] = []

    if settings.kubeconfig:
        try:
            config.load_kube_config(config_file=settings.kubeconfig, context=ctx)
            return "explicit-kubeconfig", settings.kube_context or _current_context()
        except Exception as exc:  # noqa: BLE001 - report and fall through to the next path
            attempts.append(f"explicit kubeconfig {settings.kubeconfig}: {exc}")

    if _in_cluster():
        try:
            config.load_incluster_config()
            return "in-cluster", "in-cluster"
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"in-cluster: {exc}")

    try:
        config.load_kube_config(context=ctx)
        return "default-kubeconfig", settings.kube_context or _current_context()
    except Exception as exc:  # noqa: BLE001
        attempts.append(f"default kubeconfig: {exc}")

    raise K8sConfigError(
        "Could not load any Kubernetes configuration. Tried:\n  - "
        + "\n  - ".join(attempts)
        + "\nSet ARM_KUBECONFIG and ARM_KUBE_CONTEXT, or run inside the cluster."
    )


def _current_context() -> str:
    try:
        _, active = config.list_kube_config_contexts()
        return str(active.get("name", "")) if active else ""
    except Exception:  # noqa: BLE001 - context name is cosmetic
        return ""


def _context_namespace() -> str:
    try:
        _, active = config.list_kube_config_contexts()
        if active:
            return str(active.get("context", {}).get("namespace", "") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _resolve_namespace(settings: Settings) -> str:
    if settings.namespace:
        return settings.namespace
    if SA_NAMESPACE_FILE.exists():
        value = SA_NAMESPACE_FILE.read_text().strip()
        if value:
            return value
    value = _context_namespace()
    if value:
        return value
    raise K8sConfigError(
        "No namespace could be resolved. Set ARM_NAMESPACE, or select a kubeconfig "
        "context that specifies a namespace."
    )


@lru_cache
def get_clients() -> KubeClients:
    """Build the API handles once per process."""
    settings = get_settings()
    source, context = _load_config(settings)
    namespace = _resolve_namespace(settings)
    log.info("kube.config.loaded", source=source, context=context, namespace=namespace)
    return KubeClients(
        core=client.CoreV1Api(),
        apps=client.AppsV1Api(),
        custom=client.CustomObjectsApi(),
        auth=client.AuthorizationV1Api(),
        version=client.VersionApi(),
        namespace=namespace,
        context=context,
        source=source,
    )


def _can_i(clients: KubeClients, group: str, resource: str, verb: str, subresource: str) -> bool:
    """One SelfSubjectAccessReview. Cluster-scoped checks pass namespace=None."""
    namespace = None if resource == "nodes" else clients.namespace
    review = client.V1SelfSubjectAccessReview(
        spec=client.V1SelfSubjectAccessReviewSpec(
            resource_attributes=client.V1ResourceAttributes(
                namespace=namespace,
                group=group,
                resource=resource,
                subresource=subresource or None,
                verb=verb,
            )
        )
    )
    try:
        result = clients.auth.create_self_subject_access_review(review, _request_timeout=10)
        return bool(result.status.allowed)
    except ApiException as exc:
        log.warning("kube.accessreview.failed", resource=resource, verb=verb, status=exc.status)
        return False


@lru_cache
def probe_capabilities() -> Capabilities:
    """Discover what this credential can do. Cached for the process lifetime."""
    clients = get_clients()
    caps = Capabilities()

    for label, (group, resource, verb, subresource) in _ACCESS_CHECKS.items():
        caps.access[label] = _can_i(clients, group, resource, verb, subresource)

    # metrics-server: an access review is not enough, the API has to actually serve.
    try:
        clients.custom.list_namespaced_custom_object(
            group=METRICS_GROUP,
            version=METRICS_VERSION,
            namespace=clients.namespace,
            plural="pods",
            _request_timeout=10,
        )
        caps.metrics_server = True
    except ApiException as exc:
        log.warning("kube.metrics.unavailable", status=exc.status)
        caps.degraded.append("metrics.k8s.io")

    if caps.access.get("resourcequotas_list"):
        try:
            quotas = clients.core.list_namespaced_resource_quota(
                clients.namespace, _request_timeout=10
            )
            caps.resourcequota_present = len(quotas.items) > 0
        except ApiException:
            caps.degraded.append("resourcequotas")
        try:
            ranges = clients.core.list_namespaced_limit_range(
                clients.namespace, _request_timeout=10
            )
            caps.limitrange_present = len(ranges.items) > 0
        except ApiException:
            caps.degraded.append("limitranges")

    for kind, (group, version, plural) in ARANGO_CRS.items():
        try:
            clients.custom.list_namespaced_custom_object(
                group=group,
                version=version,
                namespace=clients.namespace,
                plural=plural,
                limit=1,
                _request_timeout=10,
            )
            caps.arango_crs.append(kind)
        except ApiException as exc:
            log.info("kube.cr.unavailable", kind=kind, status=exc.status)
            caps.degraded.append(plural)

    log.info(
        "kube.capabilities.probed",
        metrics=caps.metrics_server,
        crs=len(caps.arango_crs),
        degraded=caps.degraded,
    )
    return caps

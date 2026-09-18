"""Fake Kubernetes clients for HTTP integration tests.

The smoke suite has a read-only replay client. These add the extra surface the
pages and actions actually touch: pod GET/logs, scale/delete, and optional
failures so degrade paths can be asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kubernetes.client.exceptions import ApiException

from app.config import Settings, get_settings
from app.k8s.client import METRICS_GROUP, Capabilities, get_clients, probe_capabilities
from app.main import app
from tests.conftest import fixture_items

NAMESPACE = "example-platform"

_CUSTOM = {
    "arangoplatformservices": "arangoplatformservices",
    "arangoplatformcharts": "arangoplatformcharts",
    "arangoroutes": "arangoroutes",
    "arangodeployments": "arangodeployments",
}


class _Api:
    @staticmethod
    def sanitize_for_serialization(value: Any) -> Any:
        return value


class _LogBody:
    def __init__(self, data: bytes) -> None:
        self.data = data


def _api_error(status: int, reason: str, body: str = "") -> ApiException:
    exc = ApiException(status=status, reason=reason)
    exc.body = body
    return exc


class FakeCore:
    def __init__(self, owner: FakeClients) -> None:
        self._owner = owner
        self.api_client = _Api()

    def list_namespaced_pod(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("pods")
        return {"items": fixture_items("pods")}

    def list_namespaced_event(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("events")
        if self._owner.fail_events:
            raise _api_error(403, "Forbidden", "events forbidden")
        return {"items": fixture_items("events")}

    def list_namespaced_resource_quota(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("resourcequotas")
        return {"items": fixture_items("resourcequotas")}

    def read_namespaced_pod(self, name: str, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append(f"pod:{name}")
        for item in fixture_items("pods"):
            if item.get("metadata", {}).get("name") == name:
                return item
        raise _api_error(404, "Not Found")

    def read_namespaced_pod_log(self, name: str, namespace: str = "", **kwargs: Any) -> _LogBody:
        self._owner.reads.append(f"log:{name}")
        mode = self._owner.log_mode
        if mode == "not_found":
            raise _api_error(404, "Not Found")
        if mode == "need_container" and not kwargs.get("container"):
            raise _api_error(
                400,
                "Bad Request",
                "a container name must be specified, choose one of: [api proxy]",
            )
        if mode == "no_previous" and kwargs.get("previous"):
            container = kwargs.get("container") or "api"
            raise _api_error(
                400,
                "Bad Request",
                f'previous terminated container "{container}" not found',
            )
        return _LogBody(b"line one\nline two\n")

    def delete_namespaced_pod(self, name: str, _ns: str, **kwargs: Any) -> None:
        self._owner.calls.append(("delete_pod", {"name": name, **kwargs}))


class FakeApps:
    def __init__(self, owner: FakeClients) -> None:
        self._owner = owner

    def list_namespaced_deployment(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("deployments")
        return {"items": fixture_items("deployments")}

    def list_namespaced_stateful_set(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("statefulsets")
        return {"items": fixture_items("statefulsets")}

    def list_namespaced_replica_set(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        self._owner.reads.append("replicasets")
        return {"items": fixture_items("replicasets")}

    def patch_namespaced_deployment_scale(
        self, name: str, _ns: str, body: dict[str, Any], **kwargs: Any
    ) -> None:
        self._owner.calls.append(("scale_deployment", {"name": name, "body": body, **kwargs}))

    def patch_namespaced_stateful_set_scale(
        self, name: str, _ns: str, body: dict[str, Any], **kwargs: Any
    ) -> None:
        self._owner.calls.append(("scale_sts", {"name": name, "body": body, **kwargs}))

    def patch_namespaced_deployment(
        self, name: str, _ns: str, body: dict[str, Any], **kwargs: Any
    ) -> None:
        self._owner.calls.append(("patch_deployment", {"name": name, "body": body, **kwargs}))

    def patch_namespaced_stateful_set(
        self, name: str, _ns: str, body: dict[str, Any], **kwargs: Any
    ) -> None:
        self._owner.calls.append(("patch_sts", {"name": name, "body": body, **kwargs}))


class FakeCustom:
    def __init__(self, owner: FakeClients) -> None:
        self._owner = owner

    def list_namespaced_custom_object(
        self, group: str = "", plural: str = "", **_kw: Any
    ) -> dict[str, Any]:
        self._owner.reads.append(f"custom:{plural}")
        if group == METRICS_GROUP:
            if self._owner.fail_metrics:
                raise _api_error(404, "Not Found", "metrics.k8s.io unavailable")
            return {"items": fixture_items("podmetrics")}
        return {"items": fixture_items(_CUSTOM[plural])}

    def patch_namespaced_custom_object(
        self, name: str, body: dict[str, Any], **kwargs: Any
    ) -> None:
        self._owner.calls.append(("patch_cr", {"name": name, "body": body, **kwargs}))


class FakeVersion:
    def get_code(self, **_kw: Any) -> Any:
        return type("Version", (), {"major": "1", "minor": "31"})()


@dataclass
class FakeClients:
    """Replay fixtures; record mutations; optionally fail a slice."""

    namespace: str = NAMESPACE
    context: str = "fixture"
    source: str = "fixture"
    fail_metrics: bool = False
    fail_events: bool = False
    log_mode: str = "ok"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.core = FakeCore(self)
        self.apps = FakeApps(self)
        self.custom = FakeCustom(self)
        self.version = FakeVersion()


def mount_app(
    clients: FakeClients,
    settings: Settings | None = None,
    caps: Capabilities | None = None,
) -> None:
    """Point FastAPI at these fakes for the duration of a test."""
    app.dependency_overrides[get_clients] = lambda: clients
    app.dependency_overrides[get_settings] = lambda: settings or Settings()
    app.dependency_overrides[probe_capabilities] = lambda: caps or fake_capabilities()


def fake_capabilities(*, metrics_server: bool = True) -> Capabilities:
    return Capabilities(
        access={
            "pods_list": True,
            "pods_delete": True,
            "pods_log": True,
            "deployments_list": True,
            "deployments_patch": True,
            "deployments_scale": True,
            "statefulsets_list": True,
            "statefulsets_scale": True,
        },
        metrics_server=metrics_server,
        arango_crs=["ArangoPlatformService", "ArangoDeployment"],
    )

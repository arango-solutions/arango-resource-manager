"""Smoke test: the assembled app boots and serves every page's data.

The other suites test units. This one wires the real FastAPI app to a client
that replays the recorded fixtures, then walks the routes each page actually
calls. It is the gate for the failure the unit tests cannot see - every part
works, but the app does not come up, a router is not registered, or a response
does not survive its own response_model.

No cluster, no network: the fake answers exactly the calls `_fetch` and
`metrics.fetch_usage` make, and nothing else.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.k8s.client import METRICS_GROUP, get_clients
from app.main import app
from app.services import inventory as inventory_service
from app.services import metrics
from tests.conftest import fixture_items

NAMESPACE = "example-platform"

# plural -> fixture, for the custom-resource reads.
_CUSTOM: dict[str, str] = {
    "arangoplatformservices": "arangoplatformservices",
    "arangoplatformcharts": "arangoplatformcharts",
    "arangoroutes": "arangoroutes",
    "arangodeployments": "arangodeployments",
}


class _Api:
    """`sanitize_for_serialization` on already-plain fixture dicts is identity."""

    @staticmethod
    def sanitize_for_serialization(value: Any) -> Any:
        return value


class _Core:
    api_client = _Api()

    def list_namespaced_pod(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("pods")}

    def list_namespaced_event(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("events")}

    def list_namespaced_resource_quota(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("resourcequotas")}


class _Apps:
    def list_namespaced_deployment(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("deployments")}

    def list_namespaced_stateful_set(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("statefulsets")}

    def list_namespaced_replica_set(self, _ns: str, **_kw: Any) -> dict[str, Any]:
        return {"items": fixture_items("replicasets")}


class _Custom:
    def list_namespaced_custom_object(
        self, group: str = "", plural: str = "", **_kw: Any
    ) -> dict[str, Any]:
        if group == METRICS_GROUP:
            return {"items": fixture_items("podmetrics")}
        return {"items": fixture_items(_CUSTOM[plural])}


class FakeClients:
    """Replays fixtures through the exact surface the read path uses."""

    namespace = NAMESPACE
    core = _Core()
    apps = _Apps()
    custom = _Custom()


@pytest.fixture
def client() -> Any:
    """The real app, served from fixtures.

    Both caches are dropped around the test: they are module-level and TTL'd,
    so a snapshot left behind by another test would make this one pass without
    exercising anything.
    """
    inventory_service.invalidate()
    metrics.invalidate()
    app.dependency_overrides[get_clients] = FakeClients
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        inventory_service.invalidate()
        metrics.invalidate()


def test_health_needs_no_cluster(client: Any) -> None:
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/snapshot",
        "/api/v1/services",
        "/api/v1/workloads",
        "/api/v1/pods",
        "/api/v1/genai/projects",
    ],
)
def test_every_page_route_answers(client: Any, route: str) -> None:
    """A 500 here means the app is broken in a way no unit test would catch."""
    response = client.get(route)
    assert response.status_code == 200, f"{route} -> {response.status_code} {response.text[:200]}"


def test_the_snapshot_is_populated_not_merely_valid(client: Any) -> None:
    """An empty namespace also serializes cleanly, and would pass a status check."""
    snapshot = client.get("/api/v1/snapshot").json()
    assert snapshot["namespace"] == NAMESPACE
    assert len(snapshot["pods"]) > 10
    assert len(snapshot["services"]) > 5
    assert any(w["desired_replicas"] > 0 for w in snapshot["workloads"])


def test_usage_reaches_the_response(client: Any) -> None:
    """The metrics path is separately cached and separately degradable.

    Reclaimable CPU is the number the whole tool exists to show, and it is
    None whenever usage is missing - so a silent metrics failure would empty
    the Overview while every route still returned 200.
    """
    pods = client.get("/api/v1/pods").json()
    with_usage = [p for p in pods if (p["resources"]["usage"]["cpu_cores"] or 0) > 0]
    assert with_usage, "no pod carried usage - the metrics path did not run"


def test_genai_projects_pair_their_components(client: Any) -> None:
    """The GenAI tab's whole claim is that it links a project to its retriever."""
    projects = client.get("/api/v1/genai/projects").json()
    assert projects
    assert all(p.get("status") for p in projects)


def test_stop_refuses_while_read_only(client: Any) -> None:
    """The kill switch is the safety property, so the smoke test proves it holds.

    Asserted against a workload that really exists in the fixtures: a refusal
    aimed at a missing name would pass whether or not the switch worked.
    """
    name = "arangodb-graphrag-retriever-icnn5"
    assert any(w["name"] == name for w in client.get("/api/v1/workloads").json())

    response = client.post(
        "/api/v1/actions/stop",
        json={"kind": "Deployment", "name": name, "dry_run": True},
    )
    assert response.status_code == 403, f"expected a read-only refusal, got {response.text[:200]}"
    body = response.json()
    assert body["executed"] is False
    assert body["blocked_reason"]

"""HTTP integration: every page's real reads, against fixture replay.

The smoke suite only checks that a few list routes return 200. These assert
the payload each page would actually render — a 200 with empty usage or a
missing detail field is how this app goes quietly wrong.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import inventory as inventory_service
from app.services import metrics
from tests.fakes import FakeClients, mount_app

pytestmark = pytest.mark.integration

FILE_PARSER = "arangodb-file-parser"
WORKER = "arangodb-file-parser-worker-default"


@pytest.fixture
def client() -> Any:
    inventory_service.invalidate()
    metrics.invalidate()
    mount_app(FakeClients())
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        inventory_service.invalidate()
        metrics.invalidate()


def _json(client: Any, path: str, **params: Any) -> Any:
    response = client.get(path, params=params or None)
    assert response.status_code == 200, f"{path} -> {response.status_code} {response.text[:300]}"
    return response.json()


@pytest.mark.parametrize(
    "route",
    [
        "/api/v1/namespace/overview",
        "/api/v1/resources/waste",
        "/api/v1/resources/unbounded",
        "/api/v1/resources/budget",
        "/api/v1/cluster/info",
        "/api/v1/database",
        "/api/v1/actions/stopped",
        "/api/v1/actions/history",
        "/api/v1/events",
    ],
)
def test_page_routes_answer(client: Any, route: str) -> None:
    _json(client, route)


def test_overview_carries_usage_and_a_budget(client: Any) -> None:
    overview = _json(client, "/api/v1/namespace/overview")
    assert overview["namespace"] == "example-platform"
    assert overview["metrics_available"] is True
    assert overview["pod_count"] > 10
    assert overview["totals"]["resources"]["usage"]["cpu_cores"]
    assert overview["budget"]["cpu_cores"]
    assert overview["budget"]["label"]


def test_waste_names_reclaimable_cpu(client: Any) -> None:
    waste = _json(client, "/api/v1/resources/waste")
    assert waste
    assert any(item["reclaimable_cpu_cores"] > 0 for item in waste)


def test_unbounded_lists_pods_without_limits(client: Any) -> None:
    unbounded = _json(client, "/api/v1/resources/unbounded")
    assert unbounded
    assert all(item["unset_limit_containers"] > 0 for item in unbounded)


def test_rollup_scopes_the_capacity_page(client: Any) -> None:
    services = _json(client, "/api/v1/resources/rollup", scope="service")
    workloads = _json(client, "/api/v1/resources/rollup", scope="workload")
    namespace = _json(client, "/api/v1/resources/rollup", scope="namespace")
    assert any(row["name"] == FILE_PARSER for row in services)
    assert any(row["name"] == WORKER for row in workloads)
    assert namespace[0]["scope"] == "namespace"


def test_service_detail_includes_workloads_pods_and_events(client: Any) -> None:
    detail = _json(client, f"/api/v1/services/{FILE_PARSER}")
    assert detail["name"] == FILE_PARSER
    assert detail["workload_count"] == 4
    assert len(detail["workloads"]) == 4
    assert len(detail["pods"]) == 32
    events = _json(client, "/api/v1/events", service=FILE_PARSER)
    assert isinstance(events, list)


def test_pod_detail_has_per_container_state(client: Any) -> None:
    pods = _json(client, "/api/v1/pods")
    worker = next(p for p in pods if p["workload"] and p["workload"]["name"] == WORKER)
    detail = _json(client, f"/api/v1/pods/{worker['name']}")
    assert detail["container_details"]
    assert detail["container_details"][0]["name"]
    assert "labels" in detail


def test_cluster_info_reports_gates_and_capabilities(client: Any) -> None:
    info = _json(client, "/api/v1/cluster/info")
    assert info["namespace"] == "example-platform"
    assert info["safety"]["read_only"] is True
    assert info["capabilities"]["pods_delete"] is True
    assert info["server_version"] == "1.31"


def test_database_page_lists_tiers(client: Any) -> None:
    status = _json(client, "/api/v1/database")
    assert status["name"]
    assert {tier["name"] for tier in status["tiers"]} >= {"agents", "dbservers", "coordinators"}
    agents = next(t for t in status["tiers"] if t["name"] == "agents")
    assert agents["scalable"] is False
    assert agents["policy"] == "immutable"


def test_pod_logs_return_plain_text(client: Any) -> None:
    pods = _json(client, "/api/v1/pods")
    worker = next(p for p in pods if p["workload"] and p["workload"]["name"] == WORKER)
    response = client.get(f"/api/v1/pods/{worker['name']}/logs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "line one" in response.text

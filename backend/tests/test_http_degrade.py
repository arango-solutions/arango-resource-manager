"""HTTP integration: a failed slice must degrade, not invent zeros."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import inventory as inventory_service
from app.services import metrics
from tests.fakes import FakeClients, fake_capabilities, mount_app


@pytest.fixture
def kube() -> FakeClients:
    return FakeClients()


def _client(kube: FakeClients) -> TestClient:
    inventory_service.invalidate()
    metrics.invalidate()
    mount_app(kube, caps=fake_capabilities(metrics_server=not kube.fail_metrics))
    return TestClient(app)


def test_metrics_outage_leaves_usage_unknown(kube: FakeClients) -> None:
    kube.fail_metrics = True
    with _client(kube) as client:
        try:
            overview = client.get("/api/v1/namespace/overview").json()
            assert overview["metrics_available"] is False
            assert "metrics.k8s.io" in overview["degraded"]
            pods = client.get("/api/v1/pods").json()
            assert all(p["resources"]["usage"]["cpu_cores"] is None for p in pods)
        finally:
            app.dependency_overrides.clear()
            inventory_service.invalidate()
            metrics.invalidate()


def test_events_outage_does_not_take_down_service_detail(kube: FakeClients) -> None:
    kube.fail_events = True
    with _client(kube) as client:
        try:
            response = client.get("/api/v1/services/arangodb-file-parser")
            assert response.status_code == 200, response.text[:300]
            detail = response.json()
            assert detail["workloads"]
            assert detail["events"] == []
        finally:
            app.dependency_overrides.clear()
            inventory_service.invalidate()
            metrics.invalidate()


def test_log_route_explains_a_multi_container_pod(kube: FakeClients) -> None:
    kube.log_mode = "need_container"
    with _client(kube) as client:
        try:
            pods = client.get("/api/v1/pods").json()
            name = pods[0]["name"]
            response = client.get(f"/api/v1/pods/{name}/logs")
            assert response.status_code == 400
            assert "several containers" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
            inventory_service.invalidate()
            metrics.invalidate()


def test_log_route_explains_missing_previous_instance(kube: FakeClients) -> None:
    kube.log_mode = "no_previous"
    with _client(kube) as client:
        try:
            pods = client.get("/api/v1/pods").json()
            name = pods[0]["name"]
            response = client.get(f"/api/v1/pods/{name}/logs", params={"previous": True})
            assert response.status_code == 400
            assert "not terminated before" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
            inventory_service.invalidate()
            metrics.invalidate()


def test_log_route_404s_an_unknown_pod(kube: FakeClients) -> None:
    kube.log_mode = "not_found"
    with _client(kube) as client:
        try:
            response = client.get("/api/v1/pods/no-such-pod/logs")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
            inventory_service.invalidate()
            metrics.invalidate()

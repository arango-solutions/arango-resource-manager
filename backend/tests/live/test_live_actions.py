"""Opt-in tests against a real cluster.

Skipped unless ARM_LIVE_TESTS=1. Creates a throwaway Deployment named
`arm-itest-*`, exercises dry-run then stop/restore, and deletes it.

Do not point this at an ArangoDeployment or a production Platform service.
The deployment is pause:3.9, one replica, and is always torn down.
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.k8s.client import get_clients
from app.main import app
from app.services import inventory as inventory_service
from app.services import metrics

pytestmark = pytest.mark.live

_POLL_SECONDS = 60


def _deployment(name: str) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": {"arm-itest": "true"}},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [
                        {
                            "name": "pause",
                            "image": "registry.k8s.io/pause:3.9",
                            "resources": {
                                "requests": {"cpu": "1m", "memory": "8Mi"},
                                "limits": {"cpu": "10m", "memory": "16Mi"},
                            },
                        }
                    ]
                },
            },
        },
    }


def _wait_for_workload(client: TestClient, name: str) -> dict:
    deadline = time.monotonic() + _POLL_SECONDS
    last: list[dict] = []
    while time.monotonic() < deadline:
        inventory_service.invalidate()
        last = client.get("/api/v1/workloads").json()
        found = next((w for w in last if w["name"] == name), None)
        if found is not None:
            return found
        time.sleep(2)
    pytest.fail(f"{name} never appeared in inventory; last count={len(last)}")


def test_throwaway_deployment_stop_and_restore() -> None:
    settings = get_settings()
    if settings.read_only:
        pytest.fail("ARM_READ_ONLY must be false to run live action tests.")

    kube = get_clients()
    name = f"arm-itest-{uuid.uuid4().hex[:8]}"
    inventory_service.invalidate()
    metrics.invalidate()

    kube.apps.create_namespaced_deployment(kube.namespace, _deployment(name))
    try:
        with TestClient(app) as client:
            workload = _wait_for_workload(client, name)
            assert workload["protection"]["level"] == "normal"

            dry = client.post(
                "/api/v1/actions/stop",
                json={"kind": "Deployment", "name": name, "dry_run": True},
            )
            assert dry.status_code == 200, dry.text[:300]
            assert dry.json()["plan"]["server_dry_run"] == "accepted"
            assert dry.json()["executed"] is False

            real = client.post(
                "/api/v1/actions/stop",
                json={"kind": "Deployment", "name": name, "dry_run": False},
            )
            assert real.status_code == 200, real.text[:300]
            assert real.json()["executed"] is True
            stopped = client.get("/api/v1/actions/stopped").json()
            assert stopped[f"Deployment/{name}"]["previous_replicas"] == 1

            restored = client.post(
                "/api/v1/actions/restore",
                json={"kind": "Deployment", "name": name, "dry_run": False},
            )
            assert restored.status_code == 200, restored.text[:300]
            assert f"Deployment/{name}" not in client.get("/api/v1/actions/stopped").json()
    finally:
        kube.apps.delete_namespaced_deployment(name, kube.namespace)
        inventory_service.invalidate()
        metrics.invalidate()

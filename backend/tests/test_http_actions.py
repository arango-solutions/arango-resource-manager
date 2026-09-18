"""HTTP integration: the action confirm ladder, end to end.

Unit tests call plan/execute directly. These go through the routes the UI
posts to, with a recording kube client and a temp state file, so a missing
field, an unregistered route, or a cache that is not invalidated after a
mutation shows up here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services import inventory as inventory_service
from app.services import metrics
from app.store.state import StateStore
from tests.fakes import FakeClients, mount_app

pytestmark = pytest.mark.integration

WORKER = "arangodb-file-parser-worker-default"
FILE_PARSER = "arangodb-file-parser"


@pytest.fixture
def kube() -> FakeClients:
    return FakeClients()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StateStore:
    state = StateStore(tmp_path / "state.json")
    monkeypatch.setattr("app.store.state._store", state)
    return state


@pytest.fixture
def client(kube: FakeClients, store: StateStore) -> Any:
    inventory_service.invalidate()
    metrics.invalidate()
    mount_app(kube, settings=Settings(read_only=False))
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        inventory_service.invalidate()
        metrics.invalidate()


def _action(client: Any, path: str, body: dict[str, Any], expected: int = 200) -> dict[str, Any]:
    response = client.post(path, json=body)
    assert response.status_code == expected, (
        f"{path} -> {response.status_code} {response.text[:300]}"
    )
    return response.json()


def test_dry_run_kill_validates_and_changes_nothing(
    client: Any, kube: FakeClients, store: StateStore
) -> None:
    body = _action(
        client, "/api/v1/actions/kill", {"kind": "Deployment", "name": WORKER, "dry_run": True}
    )
    assert body["executed"] is False
    assert body["plan"]["server_dry_run"] == "accepted"
    assert body["plan"]["force"] is True
    assert body["plan"]["targets"][0]["name"] == WORKER
    assert all(kwargs.get("dry_run") == "All" for _, kwargs in kube.calls)
    assert store.get_stop("example-platform", "Deployment", WORKER) is None
    assert client.get("/api/v1/actions/history").json() == []


def test_kill_then_restore_through_http(client: Any, kube: FakeClients, store: StateStore) -> None:
    body = _action(
        client, "/api/v1/actions/kill", {"kind": "Deployment", "name": WORKER, "dry_run": False}
    )
    assert body["executed"] is True
    assert body["plan"]["restore_to"] == 5

    scales = [kwargs for call, kwargs in kube.calls if call == "scale_deployment"]
    deletes = [kwargs for call, kwargs in kube.calls if call == "delete_pod"]
    assert scales[0]["body"] == {"spec": {"replicas": 0}}
    assert "dry_run" not in scales[0]
    assert deletes
    assert all(item["grace_period_seconds"] == 0 for item in deletes)

    stopped = client.get("/api/v1/actions/stopped").json()
    assert stopped[f"Deployment/{WORKER}"]["previous_replicas"] == 5

    history = client.get("/api/v1/actions/history").json()
    assert history[0]["action"] == "kill"
    assert history[0]["result"] == "ok"

    reads_before = kube.reads.count("pods")
    client.get("/api/v1/workloads")
    assert kube.reads.count("pods") > reads_before, "inventory cache was not invalidated"

    kube.calls.clear()
    restored = _action(
        client,
        "/api/v1/actions/restore",
        {"kind": "Deployment", "name": WORKER, "dry_run": False},
    )
    assert restored["executed"] is True
    assert kube.calls[0][0] == "scale_deployment"
    assert kube.calls[0][1]["body"] == {"spec": {"replicas": 5}}
    assert f"Deployment/{WORKER}" not in client.get("/api/v1/actions/stopped").json()


def test_stop_records_the_count_without_deleting_pods(client: Any, kube: FakeClients) -> None:
    body = _action(
        client,
        "/api/v1/actions/stop",
        {"kind": "Deployment", "name": WORKER, "dry_run": False},
    )
    assert body["plan"]["force"] is False
    assert body["plan"]["targets"] == []
    assert [call for call, _ in kube.calls] == ["scale_deployment"]
    assert kube.calls[0][1]["body"] == {"spec": {"replicas": 0}}


def test_delete_pod_warns_that_it_frees_nothing(client: Any, kube: FakeClients) -> None:
    pod = next(
        p
        for p in client.get("/api/v1/pods").json()
        if p["workload"] and p["workload"]["name"] == WORKER
    )
    body = _action(
        client,
        f"/api/v1/actions/pods/{pod['name']}/delete",
        {"dry_run": True, "force": True},
    )
    assert body["executed"] is False
    assert body["plan"]["force"] is True
    assert body["plan"]["targets"] == []
    warning = body["plan"]["warning"] or ""
    assert "frees nothing" in warning
    assert kube.calls[0][0] == "delete_pod"
    assert kube.calls[0][1]["dry_run"] == "All"


def test_kill_service_scales_every_file_parser_workload(client: Any, kube: FakeClients) -> None:
    body = _action(
        client,
        f"/api/v1/actions/services/{FILE_PARSER}/kill",
        {"dry_run": False},
    )
    assert body["executed"] is True
    assert {t["name"] for t in body["plan"]["targets"]} == {
        "arangodb-file-parser-api",
        "arangodb-file-parser-orchestrator",
        "arangodb-file-parser-worker-default",
        "arangodb-file-parser-worker-pdf",
    }
    scales = [kwargs for call, kwargs in kube.calls if call == "scale_deployment"]
    assert len(scales) == 4
    stopped = client.get("/api/v1/actions/stopped").json()
    assert f"Deployment/{WORKER}" in stopped


def test_protected_service_kill_is_409(client: Any, kube: FakeClients) -> None:
    body = _action(
        client,
        "/api/v1/actions/services/arangodb-cluster/kill",
        {"dry_run": True},
        expected=409,
    )
    assert body["blocked_reason"] == "protected"
    assert body["executed"] is False
    assert kube.calls == []


def test_protected_pod_delete_is_409(client: Any, kube: FakeClients) -> None:
    pod = next(p for p in client.get("/api/v1/pods").json() if p["service"] == "arangodb-cluster")
    body = _action(
        client,
        f"/api/v1/actions/pods/{pod['name']}/delete",
        {"dry_run": True, "force": True},
        expected=409,
    )
    assert body["blocked_reason"] == "protected"
    assert kube.calls == []


def test_unknown_workload_is_404(client: Any) -> None:
    body = _action(
        client,
        "/api/v1/actions/kill",
        {"kind": "Deployment", "name": "no-such-thing", "dry_run": True},
        expected=404,
    )
    assert body["blocked_reason"] == "not_found"

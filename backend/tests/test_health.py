"""The health route must not require a cluster."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_does_not_touch_the_cluster() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

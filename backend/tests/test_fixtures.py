"""Guards on the recorded fixtures: they must stay usable and stay clean."""

from __future__ import annotations

from typing import Any


def _walk(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        return [d for item in node for d in _walk(item)]
    if isinstance(node, dict):
        return [node] + [d for value in node.values() for d in _walk(value)]
    return []


def test_pod_fixtures_carry_resources(pods: list[dict[str, Any]]) -> None:
    assert pods, "expected recorded pods"
    containers = [c for p in pods for c in p["spec"]["containers"]]
    assert any(c.get("resources", {}).get("requests") for c in containers)


def test_fixtures_never_carry_env_or_managed_fields(pods: list[dict[str, Any]]) -> None:
    # Fixtures are committed. Environment variables can hold credentials, and
    # managedFields is pure bulk; the probe strips both.
    for node in _walk(pods):
        assert "env" not in node
        assert "envFrom" not in node
        assert "managedFields" not in node


def test_arango_deployment_exposes_tier_counts(arango_deployment: dict[str, Any]) -> None:
    spec = arango_deployment["spec"]
    for tier in ("agents", "dbservers", "coordinators"):
        assert spec[tier]["count"] >= 1

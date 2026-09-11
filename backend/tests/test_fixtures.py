"""Guards on the recorded fixtures: they must stay usable and stay clean."""

from __future__ import annotations

from typing import Any

from app.services.genai import ENV_KEYS


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


def test_fixtures_carry_only_allowlisted_env(pods: list[dict[str, Any]]) -> None:
    # Fixtures are committed, and an environment variable can hold a credential.
    # The probe keeps only the allowlisted names that identify a GenAI project,
    # and only where the value is literal - never a secret or field reference.
    for node in _walk(pods):
        assert "envFrom" not in node
        assert "managedFields" not in node
        for entry in node.get("env") or []:
            assert entry.get("name") in ENV_KEYS
            assert entry.get("valueFrom") is None
            assert entry.get("value") is not None


def test_arango_deployment_exposes_tier_counts(arango_deployment: dict[str, Any]) -> None:
    spec = arango_deployment["spec"]
    for tier in ("agents", "dbservers", "coordinators"):
        assert spec[tier]["count"] >= 1

"""Guards on the recorded fixtures: they must stay usable and stay clean."""

from __future__ import annotations

from typing import Any

from app.services.attribution import DATABASE_KEYS, PROJECT_KEYS


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
    """Fixtures are committed, so environment must never arrive wholesale.

    The attribution layer consumes two keys, so `env` can no longer be stripped
    outright - but every other key, and every `valueFrom` reference, must still
    be gone by the time a fixture is written. This guard is the reason the probe
    uses an allowlist rather than a denylist.
    """
    allowed = set(PROJECT_KEYS) | set(DATABASE_KEYS)
    for node in _walk(pods):
        assert "envFrom" not in node
        assert "managedFields" not in node
        for entry in node.get("env") or []:
            assert entry.get("name") in allowed, f"unexpected env in fixture: {entry.get('name')}"
            assert "valueFrom" not in entry, "a secret reference reached a committed fixture"
            assert isinstance(entry.get("value"), str)


def test_fixtures_retain_the_attribution_env(pods: list[dict[str, Any]]) -> None:
    """Without this the attribution tests would pass vacuously."""
    names = {e["name"] for p in _walk(pods) for e in (p.get("env") or [])}
    assert "db_name" in names


def test_arango_deployment_exposes_tier_counts(arango_deployment: dict[str, Any]) -> None:
    spec = arango_deployment["spec"]
    for tier in ("agents", "dbservers", "coordinators"):
        assert spec[tier]["count"] >= 1

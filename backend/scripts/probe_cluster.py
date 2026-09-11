"""Read-only cluster probe.

Prints what this credential can see and do. With --dump, records the raw API
responses into tests/fixtures/ so the unit tests can run with no cluster access.

    uv run python scripts/probe_cluster.py
    uv run python scripts/probe_cluster.py --dump
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kubernetes.client.exceptions import ApiException

from app.k8s.client import (
    ARANGO_CRS,
    METRICS_GROUP,
    METRICS_VERSION,
    get_clients,
    probe_capabilities,
)
from app.services.genai import ENV_KEYS

# Fields stripped before a fixture is written: noisy, large, or potentially sensitive.
_DROP_ANNOTATIONS = {"kubectl.kubernetes.io/last-applied-configuration"}
_DROP_CONTAINER_FIELDS = (
    "envFrom",
    "volumeMounts",
    "args",
    "command",
    "livenessProbe",
    "readinessProbe",
    "startupProbe",
    "lifecycle",
)


def _scrub(node: Any) -> Any:
    """Strip bloat and literal secrets from a recorded API response, in place.

    Fixtures are committed, so they must carry structure without carrying values.
    Container entries are reduced to the fields this app reads (name, image,
    resources, and the allowlisted environment names that identify a GenAI
    project); every other environment entry, along with mounts, args and probes,
    is dropped so no literal secret is ever committed. Helm chart payloads and
    managedFields go too - nothing here reads them and they dominate the size.
    """
    if isinstance(node, list):
        return [_scrub(item) for item in node]
    if not isinstance(node, dict):
        return node

    node.pop("managedFields", None)
    # Base64 Helm chart tarballs on ArangoPlatformChart spec/status.
    if isinstance(node.get("definition"), str) and len(node["definition"]) > 256:
        node["definition"] = "<stripped>"

    annotations = node.get("annotations")
    if isinstance(annotations, dict):
        for key in _DROP_ANNOTATIONS:
            annotations.pop(key, None)

    # A container entry: keep only what the app reads. Mounts, args and probes
    # are pure bulk, and every environment variable outside the GenAI allowlist
    # is dropped rather than redacted, because it may carry a credential and
    # nothing here consumes it.
    if "resources" in node and "image" in node:
        for key in _DROP_CONTAINER_FIELDS:
            node.pop(key, None)
        env = _allowlisted_env(node.get("env"))
        if env:
            node["env"] = env
        else:
            node.pop("env", None)

    return {key: _scrub(value) for key, value in node.items()}


def _allowlisted_env(env: Any) -> list[dict[str, Any]]:
    """The allowlisted environment entries, and only those with a literal value.

    An entry sourced from a secret or a field reference is dropped whole: its
    name alone would say nothing, and the app never resolves one either.
    """
    if not isinstance(env, list):
        return []
    return [
        {"name": entry["name"], "value": entry["value"]}
        for entry in env
        if isinstance(entry, dict)
        and entry.get("name") in ENV_KEYS
        and entry.get("valueFrom") is None
        and entry.get("value") is not None
    ]


FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _write(name: str, payload: Any) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(json.dumps(_scrub(payload), indent=2, sort_keys=True, default=str))
    print(f"  wrote {path.relative_to(FIXTURES.parent.parent)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", action="store_true", help="record responses into tests/fixtures/")
    args = parser.parse_args()

    clients = get_clients()
    print(f"context   : {clients.context}")
    print(f"namespace : {clients.namespace}")
    print(f"source    : {clients.source}\n")

    caps = probe_capabilities()
    print("capabilities:")
    for key, value in sorted(caps.access.items()):
        print(f"  {'yes' if value else ' no'}  {key}")
    print(f"  {'yes' if caps.metrics_server else ' no'}  metrics_server")
    print(f"  resourcequota_present : {caps.resourcequota_present}")
    print(f"  limitrange_present    : {caps.limitrange_present}")
    print(f"  arango_crs            : {', '.join(caps.arango_crs) or 'none'}")
    if caps.degraded:
        print(f"  degraded              : {', '.join(caps.degraded)}")

    ns = clients.namespace
    core, apps, custom = clients.core, clients.apps, clients.custom

    sources: dict[str, Any] = {
        "pods": lambda: core.list_namespaced_pod(ns, _request_timeout=30),
        "deployments": lambda: apps.list_namespaced_deployment(ns, _request_timeout=30),
        "statefulsets": lambda: apps.list_namespaced_stateful_set(ns, _request_timeout=30),
        "replicasets": lambda: apps.list_namespaced_replica_set(ns, _request_timeout=30),
        "events": lambda: core.list_namespaced_event(ns, _request_timeout=30),
        "resourcequotas": lambda: core.list_namespaced_resource_quota(ns, _request_timeout=30),
        "limitranges": lambda: core.list_namespaced_limit_range(ns, _request_timeout=30),
        "pvcs": lambda: core.list_namespaced_persistent_volume_claim(ns, _request_timeout=30),
    }

    print("\ninventory:")
    results: dict[str, Any] = {}
    for name, fetch in sources.items():
        try:
            response = fetch()
            items = response.items
            results[name] = clients.core.api_client.sanitize_for_serialization(response)
            print(f"  {len(items):4d}  {name}")
        except ApiException as exc:
            print(f"   ---  {name} (HTTP {exc.status})")

    for _kind, (group, version, plural) in ARANGO_CRS.items():
        try:
            response = custom.list_namespaced_custom_object(
                group=group, version=version, namespace=ns, plural=plural, _request_timeout=30
            )
            results[plural] = response
            print(f"  {len(response.get('items', [])):4d}  {plural}")
        except ApiException as exc:
            print(f"   ---  {plural} (HTTP {exc.status})")

    if caps.metrics_server:
        try:
            response = custom.list_namespaced_custom_object(
                group=METRICS_GROUP,
                version=METRICS_VERSION,
                namespace=ns,
                plural="pods",
                _request_timeout=30,
            )
            results["podmetrics"] = response
            print(f"  {len(response.get('items', [])):4d}  podmetrics")
        except ApiException as exc:
            print(f"   ---  podmetrics (HTTP {exc.status})")

    if args.dump:
        print("\nrecording fixtures:")
        for name, payload in results.items():
            _write(name, payload)
        _write("capabilities", caps.as_dict())

    return 0


if __name__ == "__main__":
    sys.exit(main())

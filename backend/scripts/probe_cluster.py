"""Read-only cluster probe.

Prints what this credential can see and do. With --dump, records the raw API
responses into tests/fixtures/ so the unit tests can run with no cluster access.

    uv run python scripts/probe_cluster.py
    uv run python scripts/probe_cluster.py --dump
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
from app.services.genai import DB_ENV, ENV_KEYS, PROJECT_ENV

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


# Cluster addressing. Nothing in the app reads a pod or host IP, so they are
# dropped outright. Node names ARE read (a pod summary shows where it runs), so
# they are pseudonymized instead of dropped.
_DROP_ADDRESS_FIELDS = ("podIP", "podIPs", "hostIP", "hostIPs")

# `ip-10-0-0-170.example.internal` and friends: the cloud provider encodes the
# private address into the node name, so the name itself is VPC topology.
_NODE_NAME_RE = re.compile(r"\bip(?:-\d{1,3}){4}\b")

# Node topology labels: `topology.kubernetes.io/region` and `/zone` say where in
# the world the cluster runs. The zone pattern is listed first because a zone is
# a region plus a letter, and the region pattern would otherwise claim its prefix.
_ZONE_RE = re.compile(r"\b(?:us|eu|ap|sa|ca|me|af)-[a-z]+-\d[a-z]\b")
_REGION_RE = re.compile(r"\b(?:us|eu|ap|sa|ca|me|af)-[a-z]+-\d\b")

# The namespace name is the single most identifying string in a recording -
# `arangodb-platform-rnd-<id>` names a specific installation. It is replaced
# with the placeholder the fixtures and tests already use, so a re-recording
# stays consistent with `assemble(raw, PLACEHOLDER_NAMESPACE, ...)` instead of
# churning every test that names it.
PLACEHOLDER_NAMESPACE = "example-platform"

# Allowlisted env whose *value* identifies the installation rather than
# describing its configuration. A project name is frequently a customer's name.
# The model and provider settings are deliberately not here: they are config,
# they identify nobody, and they are more useful in a fixture as themselves.
_IDENTIFYING_ENV = frozenset({PROJECT_ENV, DB_ENV, "SERVICE_ID", "AUTOGRAPH_SERVICE_ID"})


def _pseudonym(original: str, prefix: str = "node") -> str:
    """A stable fake name for a real one.

    Deterministic on purpose: re-recording the same cluster produces identical
    fixtures, so a `probe-dump` shows a small honest diff rather than churning
    every name and burying the real change. Distinctness survives, so two pods
    on one node still share a node name and two projects on one database still
    share a database value.
    """
    digest = hashlib.sha256(original.encode()).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _depersonalize(value: str) -> str:
    """Rewrite every identifying token in one string, most specific first."""
    value = _NODE_NAME_RE.sub(lambda m: _pseudonym(m.group(0), "node"), value)
    value = _ZONE_RE.sub(lambda m: _pseudonym(m.group(0), "zone"), value)
    return _REGION_RE.sub(lambda m: _pseudonym(m.group(0), "region"), value)


def _env_value(name: str, value: str) -> str:
    """Identifying env values are pseudonymized; configuration is kept as-is."""
    if name not in _IDENTIFYING_ENV:
        return value
    prefix = "db" if name == DB_ENV else "project" if name == PROJECT_ENV else "id"
    return _pseudonym(value, prefix)


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

    for key in _DROP_ADDRESS_FIELDS:
        node.pop(key, None)

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


def _scrub_strings(node: Any, namespace: str = "") -> Any:
    """Second pass: rewrite identifying strings wherever they appear.

    A node name reaches a fixture by at least three routes - `spec.nodeName`, a
    PVC's `volume.kubernetes.io/selected-node` annotation, and ArangoDeployment
    status - and the namespace appears on every object plus inside owner
    references, route paths and event messages. So this walks values rather
    than enumerating paths. Enumerating paths is how the third route gets
    missed.

    `namespace` is the live namespace being recorded, substituted wherever it
    occurs. It is matched literally rather than by pattern, so the replacement
    is exact and cannot catch something that merely looks like a namespace.
    """
    if isinstance(node, list):
        return [_scrub_strings(item, namespace) for item in node]
    if isinstance(node, dict):
        return {key: _scrub_strings(value, namespace) for key, value in node.items()}
    if isinstance(node, str):
        value = node.replace(namespace, PLACEHOLDER_NAMESPACE) if namespace else node
        return _depersonalize(value)
    return node


def _allowlisted_env(env: Any) -> list[dict[str, Any]]:
    """The allowlisted environment entries, and only those with a literal value.

    An entry sourced from a secret or a field reference is dropped whole: its
    name alone would say nothing, and the app never resolves one either.
    """
    if not isinstance(env, list):
        return []
    return [
        {"name": entry["name"], "value": _env_value(entry["name"], entry["value"])}
        for entry in env
        if isinstance(entry, dict)
        and entry.get("name") in ENV_KEYS
        and entry.get("valueFrom") is None
        and entry.get("value") is not None
    ]


FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _write(name: str, payload: Any, namespace: str = "") -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(
        json.dumps(
            _scrub_strings(_scrub(payload), namespace), indent=2, sort_keys=True, default=str
        )
    )
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
            _write(name, payload, ns)
        _write("capabilities", caps.as_dict(), ns)

    return 0


if __name__ == "__main__":
    sys.exit(main())

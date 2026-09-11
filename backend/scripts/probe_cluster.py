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
from app.services.attribution import DATABASE_KEYS, PROJECT_KEYS

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

# Environment is consumed by the attribution layer, so it can no longer be
# dropped wholesale - but it must not be committed wholesale either. Only these
# keys survive into a fixture, and only their literal values; everything else,
# including every `valueFrom` reference, is discarded.
_KEEP_ENV_KEYS = frozenset(PROJECT_KEYS) | frozenset(DATABASE_KEYS)

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


def _pseudonym(original: str, prefix: str = "node") -> str:
    """A stable fake name for a real one.

    Deterministic on purpose: re-recording the same cluster produces identical
    fixtures, so a `probe-dump` shows a small honest diff rather than churning
    every node name and burying the real change.
    """
    digest = hashlib.sha256(original.encode()).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _depersonalize(value: str) -> str:
    """Rewrite every identifying token in one string, most specific first.

    Distinctness is preserved throughout: two pods on one node still share a
    node name, two zones remain two zones. The topology the scheduler cares
    about survives; the topology that says whose cluster this is does not.
    """
    value = _NODE_NAME_RE.sub(lambda m: _pseudonym(m.group(0), "node"), value)
    value = _ZONE_RE.sub(lambda m: _pseudonym(m.group(0), "zone"), value)
    return _REGION_RE.sub(lambda m: _pseudonym(m.group(0), "region"), value)


def _pseudonym_label(key: str, value: str) -> str:
    """A stable fake project or database name, shaped like the real one.

    Two services on the same database still share a value here, and two on
    different databases still differ, so the grouping and conflict paths behave
    exactly as they do against the live cluster.
    """
    prefix = "db" if key in DATABASE_KEYS else "project"
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:6]}"


def _scrub(node: Any) -> Any:
    """Strip bloat and literal secrets from a recorded API response, in place.

    Fixtures are committed, so they must carry structure without carrying values.
    Container entries are reduced to the fields this app reads (name, image,
    resources) plus the attribution env allowlist; all other environment
    variables, mounts, args and probes are dropped so no literal secret is ever
    committed. Helm chart payloads and managedFields go too - nothing here reads
    them and they dominate the size. Pod and host IPs go because nothing reads
    them; node names are pseudonymized by `_scrub_strings` because the app does.
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
    # are pure bulk. Environment survives only as the attribution allowlist -
    # the rest can carry credentials and nothing here consumes it.
    if "resources" in node and "image" in node:
        for key in _DROP_CONTAINER_FIELDS:
            node.pop(key, None)
        env = node.get("env")
        if isinstance(env, list):
            # The values are pseudonymized, not copied. A project name is the
            # single most identifying string a recording can carry - it is
            # frequently a customer's name - and the fixtures only need *a*
            # value to exercise the attribution path, never the real one.
            kept = [
                {"name": e["name"], "value": _pseudonym_label(e["name"], e["value"])}
                for e in env
                if isinstance(e, dict)
                and e.get("name") in _KEEP_ENV_KEYS
                and isinstance(e.get("value"), str)
            ]
            if kept:
                node["env"] = kept
            else:
                node.pop("env", None)

    return {key: _scrub(value) for key, value in node.items()}


def _scrub_strings(node: Any) -> Any:
    """Second pass: rewrite identifying strings wherever they appear.

    A node name reaches a fixture by at least three routes - `spec.nodeName`, a
    PVC's `volume.kubernetes.io/selected-node` annotation, and ArangoDeployment
    status - so this walks values rather than enumerating paths. Enumerating
    paths is how the last one gets missed.
    """
    if isinstance(node, list):
        return [_scrub_strings(item) for item in node]
    if isinstance(node, dict):
        return {key: _scrub_strings(value) for key, value in node.items()}
    if isinstance(node, str):
        return _depersonalize(node)
    return node


FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _write(name: str, payload: Any) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(
        json.dumps(_scrub_strings(_scrub(payload)), indent=2, sort_keys=True, default=str)
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
            _write(name, payload)
        _write("capabilities", caps.as_dict())

    return 0


if __name__ == "__main__":
    sys.exit(main())

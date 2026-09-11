"""Fixtures must not identify the cluster they were recorded from.

The fixtures come from a live Platform namespace, and this repository is meant
to be published. That stays safe only if the check is mechanical: a cleanup pass
someone runs after `probe-dump` is one forgotten step from committing a
customer's topology - and the commit is what outlives the decision to publish.

The probe scrubs; this fails the build when something gets through anyway. Every
rule below is here because it caught something real - speculative patterns are
left out, because a guard that cries wolf is a guard people stop reading.

When one fires, fix `scripts/probe_cluster.py` so the next recording is clean.
Editing the fixture by hand only survives until someone re-records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.probe_cluster import PLACEHOLDER_NAMESPACE, _scrub_strings

FIXTURE_DIR = Path(__file__).parent / "fixtures"

FORBIDDEN = {
    # Found 65 in committed fixtures. Private ranges only: a bare dotted quad
    # also matches an ArangoDB version ("3.12.9.1").
    "a private (VPC) IPv4 address": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
        r"|192\.168(?:\.\d{1,3}){2})\b"
    ),
    # `ip-10-0-0-170` - the provider encodes the private address into the node
    # name, so the name is itself VPC topology. Found 6.
    "a provider node name carrying a private address": re.compile(r"\bip(?:-\d{1,3}){4}\b"),
    # Both reappeared on a re-record after having been removed by hand.
    "a cloud region": re.compile(r"\b(?:us|eu|ap|sa|ca|me|af)-[a-z]+-\d\b"),
    "an availability zone": re.compile(r"\b(?:us|eu|ap|sa|ca|me|af)-[a-z]+-\d[a-z]\b"),
}

# Address-bearing by definition, and unread by the app. Checking the field
# catches a public IP without mistaking a version string for one.
ADDRESS_KEYS = frozenset({"podIP", "podIPs", "hostIP", "hostIPs", "clusterIP", "clusterIPs"})


def walk(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        return [d for item in node for d in walk(item)]
    if isinstance(node, dict):
        return [node] + [d for value in node.values() for d in walk(value)]
    return []


def fixture_files() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.json"))


def test_there_are_fixtures_to_check() -> None:
    """Otherwise every test below passes by finding nothing."""
    assert fixture_files(), "no fixtures found - this guard would be vacuous"


def test_the_app_never_imports_the_probe() -> None:
    """Anonymization must not reach what the UI shows.

    The probe exists to write fixtures. If an app module ever imported its
    scrubbing, the running tool would start displaying pseudonyms instead of
    the real service a user has to act on - which would make it useless for
    its actual job. The dependency runs one way: the probe imports the app.
    """
    app_dir = Path(__file__).parent.parent / "app"
    offenders = [
        path.relative_to(app_dir).as_posix()
        for path in app_dir.rglob("*.py")
        if "probe_cluster" in path.read_text()
    ]
    assert not offenders, (
        f"app modules import the probe: {offenders}. Anonymization belongs to "
        "fixture recording only; the live app must show real names."
    )


def test_topology_is_pseudonymized_but_still_distinct() -> None:
    """Node, region and zone are replaced, and stay distinguishable.

    Distinctness is the part worth pinning: the scheduler topology tests depend
    on two nodes still being two nodes.
    """
    first = _scrub_strings({"nodeName": "ip-10-0-0-170.eu-central-1.compute.internal"})
    second = _scrub_strings({"nodeName": "ip-10-0-0-88.eu-central-1.compute.internal"})

    for value in (first["nodeName"], second["nodeName"]):
        assert "10-0-0" not in value
        assert "eu-central-1" not in value
        assert value.startswith("node-")

    assert first["nodeName"] != second["nodeName"], "two nodes must stay two nodes"
    assert (
        first["nodeName"]
        == _scrub_strings({"nodeName": "ip-10-0-0-170.eu-central-1.compute.internal"})["nodeName"]
    ), "the same input must always give the same pseudonym"


def test_the_live_namespace_is_substituted_wherever_it_appears() -> None:
    """Not just `metadata.namespace` - it also shows up inside free text."""
    live = "arangodb-platform-rnd-a2lc79ac"
    scrubbed = _scrub_strings(
        {
            "namespace": live,
            "message": f'namespaces "{live}" is forbidden',
            "selfLink": f"/api/v1/namespaces/{live}/pods",
        },
        live,
    )
    assert live not in json.dumps(scrubbed)
    assert scrubbed["namespace"] == PLACEHOLDER_NAMESPACE
    assert PLACEHOLDER_NAMESPACE in scrubbed["message"]


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_carries_nothing_identifying(path: Path) -> None:
    text = path.read_text()
    found = [
        f"{description} ({len(matches)} distinct, e.g. {', '.join(sorted(matches)[:3])})"
        for description, pattern in FORBIDDEN.items()
        if (matches := set(pattern.findall(text)))
    ]
    assert not found, (
        f"{path.name} identifies the source cluster:\n  "
        + "\n  ".join(found)
        + "\n\nFix scripts/probe_cluster.py, not the fixture."
    )


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_names_only_the_placeholder_namespace(path: Path) -> None:
    """Checked by field, not by pattern.

    No regex separates `arangodb-platform-rnd-a2lc79ac` from the ReplicaSet
    `arangodb-platform-ui-595bc64f9c` - same shape, entirely innocent. The
    namespace is a known literal in a known field, so the exact check is both
    cheaper and correct where a pattern would only be noisy.
    """
    found = {
        node["namespace"]
        for node in walk(json.loads(path.read_text()))
        if isinstance(node.get("namespace"), str)
    }
    unexpected = found - {PLACEHOLDER_NAMESPACE}
    assert not unexpected, f"{path.name} names {sorted(unexpected)}, not {PLACEHOLDER_NAMESPACE!r}"


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_carries_no_address_fields(path: Path) -> None:
    present = {
        key for node in walk(json.loads(path.read_text())) for key in node if key in ADDRESS_KEYS
    }
    assert not present, (
        f"{path.name} carries {sorted(present)}. "
        "Add them to _DROP_ADDRESS_FIELDS in scripts/probe_cluster.py."
    )

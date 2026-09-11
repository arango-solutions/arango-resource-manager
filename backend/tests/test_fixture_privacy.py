"""Fixtures must not identify the cluster they were recorded from.

This repository is meant to be public, and its fixtures are recorded from a real
ArangoDB Platform namespace. That combination only stays safe if the check is
mechanical: an anonymization pass that a person has to remember to run after
`make probe-dump` is one forgotten step away from publishing a customer's
topology, and re-recording is exactly when attention is elsewhere.

So this test is the gate, not the probe. The probe scrubs; this fails the build
when something got through anyway.

When a pattern here fires, fix `scripts/probe_cluster.py` so the next recording
is clean at the source. Do not edit the fixture by hand — the next `probe-dump`
would reintroduce it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# Each pattern is something a recording can pick up that identifies where it
# came from. The names are the failure message, so they read as instructions.
FORBIDDEN = {
    "a cloud provider API hostname": re.compile(
        r"[A-Za-z0-9]{16,}\.(gr\d+\.)?[a-z0-9-]+\.(eks|aks|gke)\.[a-z.]+"
    ),
    "a cloud region": re.compile(
        r"\b(us|eu|ap|sa|ca|me|af)-(east|west|central|north|south|northeast|northwest|southeast|southwest)-\d\b"
    ),
    "an availability zone": re.compile(r"\b(us|eu|ap|sa|ca|me|af)-[a-z]+-\d[a-z]\b"),
    # Private ranges only. A bare dotted quad also matches an ArangoDB version
    # ("3.12.9.1") and an image tag, and a guard that cries wolf gets muted --
    # which is the failure mode this file exists to prevent. Public addresses
    # are caught structurally below instead, by the field they arrive in.
    "a private (VPC) IPv4 address": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2})\b"
    ),
    "a provider node name carrying a private address": re.compile(r"\bip(?:-\d{1,3}){4}\b"),
    "an AWS ARN": re.compile(r"arn:aws:"),
    "a cloud instance id": re.compile(r"\bi-[0-9a-f]{8,}\b"),
    "an email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w]{2,}"),
}

# Keys whose value is an address by definition. Checking the field rather than
# the text catches a public IP without mistaking a version string for one.
ADDRESS_KEYS = frozenset(
    {
        "podIP",
        "podIPs",
        "hostIP",
        "hostIPs",
        "clusterIP",
        "clusterIPs",
        "externalIPs",
        "loadBalancerIP",
    }
)


def walk(node: object) -> list[dict]:
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


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_carries_nothing_identifying(path: Path) -> None:
    text = path.read_text()
    found: list[str] = []
    for description, pattern in FORBIDDEN.items():
        matches = sorted({m if isinstance(m, str) else m[0] for m in pattern.findall(text)})
        if matches:
            sample = ", ".join(matches[:3])
            found.append(f"{description} ({len(matches)} distinct, e.g. {sample})")

    assert not found, (
        f"{path.name} contains data identifying the source cluster:\n  "
        + "\n  ".join(found)
        + "\n\nFix scripts/probe_cluster.py so the next recording is clean, "
        "rather than editing the fixture by hand."
    )


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_carries_no_address_fields(path: Path) -> None:
    """Nothing in the app reads an address, so none should survive a recording."""
    present = {
        key for node in walk(json.loads(path.read_text())) for key in node if key in ADDRESS_KEYS
    }
    assert not present, (
        f"{path.name} still carries address fields {sorted(present)}. "
        "Add them to _DROP_ADDRESS_FIELDS in scripts/probe_cluster.py."
    )


@pytest.mark.parametrize("path", fixture_files(), ids=lambda p: p.name)
def test_fixture_is_valid_json(path: Path) -> None:
    json.loads(path.read_text())

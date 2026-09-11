"""Test fixtures. Everything here is recorded data - no test touches a cluster."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a recorded API response by name, e.g. "pods"."""
    path = FIXTURE_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"fixture {name}.json is missing - run `make probe-dump`")
    return json.loads(path.read_text())


def fixture_items(name: str) -> list[dict[str, Any]]:
    return list(load_fixture(name).get("items", []))


@pytest.fixture
def pods() -> list[dict[str, Any]]:
    return fixture_items("pods")


@pytest.fixture
def deployments() -> list[dict[str, Any]]:
    return fixture_items("deployments")


@pytest.fixture
def statefulsets() -> list[dict[str, Any]]:
    return fixture_items("statefulsets")


@pytest.fixture
def platform_services() -> list[dict[str, Any]]:
    return fixture_items("arangoplatformservices")


@pytest.fixture
def arango_deployment() -> dict[str, Any]:
    items = fixture_items("arangodeployments")
    if not items:
        pytest.skip("no ArangoDeployment recorded")
    return items[0]

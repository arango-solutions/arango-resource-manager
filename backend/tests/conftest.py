"""Test fixtures. Everything here is recorded data - no test touches a cluster."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings, get_settings

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


@pytest.fixture(autouse=True)
def _ignore_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not inherit the developer's `.env`.

    `Settings` reads `.env` by default, so a local file setting
    `ARM_READ_ONLY=false` — which is exactly what you set to try an action
    against a real cluster — silently turns the safety assertions into
    assertions about your laptop. CI has no `.env`, so the suite stays green
    there and the coverage quietly disappears for whoever is actually using
    the tool. Pinning it off makes the suite say the same thing everywhere.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("ARM_"):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

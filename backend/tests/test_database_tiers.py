"""Per-tier rules for resizing the ArangoDB cluster.

These encode domain knowledge, not plumbing, and the API enforces them itself
rather than trusting the UI to disable a button.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.models.actions import BlockedReason
from app.services import arangodeployment
from app.services.actions import ActionBlocked
from tests.conftest import fixture_items


class FakeClients:
    def __init__(self, deployment: dict[str, Any]) -> None:
        self.namespace = "test-ns"
        self.patches: list[dict[str, Any]] = []
        outer = self

        class Custom:
            def list_namespaced_custom_object(self, **kwargs: Any) -> dict[str, Any]:
                return {"items": [deployment]}

            def patch_namespaced_custom_object(self, **kwargs: Any) -> None:
                outer.patches.append(kwargs)

        self.custom = Custom()


@pytest.fixture
def clients() -> FakeClients:
    return FakeClients(fixture_items("arangodeployments")[0])


ENABLED = Settings(read_only=False, allow_database_scaling=True)


def test_agents_can_never_be_scaled(clients: FakeClients) -> None:
    """The agency is a RAFT quorum. There is no flag that permits this."""
    with pytest.raises(ActionBlocked) as caught:
        arangodeployment.plan_scale(clients, ENABLED, "agents", 5)  # type: ignore[arg-type]

    assert caught.value.reason is BlockedReason.TIER_IMMUTABLE
    assert caught.value.remediation and "quorum" in caught.value.remediation
    assert clients.patches == []


def test_coordinators_scale_freely(clients: FakeClients) -> None:
    plan = arangodeployment.plan_scale(clients, ENABLED, "coordinators", 4)  # type: ignore[arg-type]
    assert plan.current_replicas == 3
    assert plan.target_replicas == 4
    assert plan.requires_typed_confirmation is False


def test_shrinking_dbservers_warns_about_draining(clients: FakeClients) -> None:
    """Shrinking dbservers moves shards. That earns the same friction as
    taking a service to zero."""
    plan = arangodeployment.plan_scale(clients, ENABLED, "dbservers", 2)  # type: ignore[arg-type]
    assert plan.requires_typed_confirmation is True
    assert plan.warning and "shards" in plan.warning


def test_growing_dbservers_is_not_gated(clients: FakeClients) -> None:
    plan = arangodeployment.plan_scale(clients, ENABLED, "dbservers", 5)  # type: ignore[arg-type]
    assert plan.requires_typed_confirmation is False


def test_a_tier_cannot_be_taken_to_zero(clients: FakeClients) -> None:
    with pytest.raises(ActionBlocked) as caught:
        arangodeployment.plan_scale(clients, ENABLED, "coordinators", 0)  # type: ignore[arg-type]
    assert caught.value.reason is BlockedReason.INVALID
    assert "stop serving" in caught.value.detail


def test_scaling_is_locked_unless_explicitly_enabled(clients: FakeClients) -> None:
    settings = Settings(read_only=False, allow_database_scaling=False)
    plan = arangodeployment.plan_scale(clients, settings, "coordinators", 4)  # type: ignore[arg-type]

    with pytest.raises(ActionBlocked) as caught:
        arangodeployment.execute(clients, settings, plan, "coordinators", dry_run=True)  # type: ignore[arg-type]

    assert caught.value.reason is BlockedReason.DATABASE_LOCKED
    assert clients.patches == []


def test_read_only_outranks_the_database_flag(clients: FakeClients) -> None:
    settings = Settings(read_only=True, allow_database_scaling=True)
    plan = arangodeployment.plan_scale(clients, ENABLED, "coordinators", 4)  # type: ignore[arg-type]

    with pytest.raises(ActionBlocked) as caught:
        arangodeployment.execute(clients, settings, plan, "coordinators", dry_run=True)  # type: ignore[arg-type]

    assert caught.value.reason is BlockedReason.READ_ONLY
    assert clients.patches == []


def test_patch_targets_the_tier_count(clients: FakeClients) -> None:
    plan = arangodeployment.plan_scale(clients, ENABLED, "coordinators", 4)  # type: ignore[arg-type]
    arangodeployment.execute(clients, ENABLED, plan, "coordinators", dry_run=False)  # type: ignore[arg-type]

    patch = clients.patches[0]
    assert patch["body"] == {"spec": {"coordinators": {"count": 4}}}
    assert patch["name"] == "deployment"
    assert "dry_run" not in patch


def test_dry_run_sends_dry_run_all(clients: FakeClients) -> None:
    plan = arangodeployment.plan_scale(clients, ENABLED, "dbservers", 4)  # type: ignore[arg-type]
    arangodeployment.execute(clients, ENABLED, plan, "dbservers", dry_run=True)  # type: ignore[arg-type]
    assert clients.patches[0]["dry_run"] == "All"

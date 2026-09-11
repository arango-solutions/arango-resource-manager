"""Capacity arithmetic, against the recorded fixtures.

The central risk here is presenting a policy number as though it were capacity.
Several of these tests exist purely to stop that.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models.common import ProtectionLevel, Resources
from app.models.inventory import InventorySnapshot
from app.models.resources import BudgetSource
from app.services import rollup
from app.services.inventory import assemble
from tests.conftest import fixture_items


def _usage() -> dict[str, Resources]:
    """Live usage, read from the recorded metrics-server response."""
    from app.services.quantities import add_optional, parse_cpu, parse_memory

    usage: dict[str, Resources] = {}
    for item in fixture_items("podmetrics"):
        name = item["metadata"]["name"]
        cpu = memory = None
        for container in item.get("containers", []):
            block = container.get("usage", {})
            cpu = add_optional(cpu, parse_cpu(block.get("cpu")))
            memory = add_optional(memory, parse_memory(block.get("memory")))
        usage[name] = Resources(cpu_cores=cpu, memory_bytes=None if memory is None else int(memory))
    return usage


@pytest.fixture
def snapshot() -> InventorySnapshot:
    raw = {
        "pods": fixture_items("pods"),
        "deployments": fixture_items("deployments"),
        "statefulsets": fixture_items("statefulsets"),
        "replicasets": fixture_items("replicasets"),
        "platform_services": fixture_items("arangoplatformservices"),
        "charts": fixture_items("arangoplatformcharts"),
        "routes": fixture_items("arangoroutes"),
        "arango_deployments": fixture_items("arangodeployments"),
        "events": fixture_items("events"),
        "resourcequotas": fixture_items("resourcequotas"),
    }
    return assemble(raw, "example-platform", Settings(), usage=_usage())


def test_the_headline_numbers(snapshot: InventorySnapshot) -> None:
    """46 cores reserved against about half a core used. The reason this exists."""
    report = rollup.namespace_report(snapshot)
    assert report.resources.requests.cpu_cores == pytest.approx(46.25, abs=0.01)
    assert report.resources.usage.cpu_cores is not None
    assert report.resources.usage.cpu_cores < 2.0
    assert report.cpu_efficiency is not None
    assert report.cpu_efficiency < 0.05
    assert report.reclaimable_cpu_cores is not None
    assert report.reclaimable_cpu_cores > 44


def test_overcommit_is_limits_over_requests(snapshot: InventorySnapshot) -> None:
    report = rollup.namespace_report(snapshot)
    assert report.resources.limits.cpu_cores == pytest.approx(140.0, abs=0.5)
    assert report.cpu_overcommit is not None
    assert report.cpu_overcommit == pytest.approx(140.0 / 46.25, abs=0.05)


def test_derived_budget_is_marked_as_policy_not_capacity(
    snapshot: InventorySnapshot,
) -> None:
    """The one mistake this module must never make.

    There is no ResourceQuota and no node access, so any budget shown here is a
    number someone chose. It has to say so.
    """
    budget = rollup.resolve_budget(rollup.total_resources(snapshot.pods), Settings())
    assert budget.source is BudgetSource.DERIVED
    assert budget.is_policy is True
    assert "derived" in budget.label
    # Derived from 46.25 reserved x 1.25 headroom, rounded to something sane.
    assert budget.cpu_cores == 64


def test_configured_budget_wins_over_derived(snapshot: InventorySnapshot) -> None:
    settings = Settings(budget_cpu_cores=100, budget_memory_gi=256)
    budget = rollup.resolve_budget(rollup.total_resources(snapshot.pods), settings)
    assert budget.source is BudgetSource.CONFIGURED
    assert budget.cpu_cores == 100
    assert budget.memory_bytes == 256 * 1024**3


def test_a_resource_quota_outranks_everything_and_is_not_policy() -> None:
    """When a real ceiling exists it is used, and marked as enforced."""
    quota = {
        "metadata": {"name": "team-quota"},
        "status": {"hard": {"requests.cpu": "80", "requests.memory": "200Gi"}},
    }
    budget = rollup.resolve_budget(rollup.total_resources([]), Settings(), quotas=[quota])
    assert budget.source is BudgetSource.QUOTA
    assert budget.is_policy is False
    assert budget.cpu_cores == 80
    assert "team-quota" in budget.label


def test_waste_ranks_the_worst_offender_first(snapshot: InventorySnapshot) -> None:
    """25 replicas reserving far more than the few millicores they use."""
    items = rollup.waste(snapshot, Settings())
    assert items
    assert items[0].name == "arangodb-file-parser-worker-pdf"
    assert items[0].replicas == 25
    assert items[0].reclaimable_cpu_cores > 20
    assert items[0].cpu_efficiency is not None
    assert items[0].cpu_efficiency < 0.05


def test_waste_is_sorted_descending(snapshot: InventorySnapshot) -> None:
    items = rollup.waste(snapshot, Settings())
    reclaimable = [item.reclaimable_cpu_cores for item in items]
    assert reclaimable == sorted(reclaimable, reverse=True)


def test_waste_never_lists_protected_workloads(snapshot: InventorySnapshot) -> None:
    """Pointing at something the reader is not allowed to act on is noise."""
    items = rollup.waste(snapshot, Settings())
    assert all(item.protection.level is not ProtectionLevel.PROTECTED for item in items)


def test_cost_is_absent_unless_rates_are_configured(
    snapshot: InventorySnapshot,
) -> None:
    """The app must never display an invented price."""
    items = rollup.waste(snapshot, Settings())
    assert all(item.cost_per_day is None for item in items)

    priced = rollup.waste(snapshot, Settings(cost_per_core_hour=0.04))
    assert priced[0].cost_per_day is not None
    assert priced[0].cost_per_day > 0


def test_unbounded_pods_are_found(snapshot: InventorySnapshot) -> None:
    pods = rollup.unbounded_pods(snapshot)
    assert pods, "this namespace has containers with no limits"
    assert all(p.unset_limit_containers > 0 for p in pods)


def test_unbounded_count_separates_what_can_be_acted_on(
    snapshot: InventorySnapshot,
) -> None:
    """Most unbounded pods here are the database, where omitting limits is the
    operator's deliberate choice. Counting them as risk overstates it."""
    result = rollup.overview(snapshot, Settings())
    assert result.pods_without_limits == 15
    assert result.pods_without_limits_actionable == 3

    pods = rollup.unbounded_pods(snapshot)
    protected = [p for p in pods if p.protection.level is ProtectionLevel.PROTECTED]
    assert len(protected) == 12
    assert all(p.service == "arangodb-cluster" for p in protected)


def test_overview_ties_the_page_together(snapshot: InventorySnapshot) -> None:
    result = rollup.overview(snapshot, Settings())
    assert result.pod_count == 59
    assert result.service_count == 15
    assert result.services_not_ready == 1
    assert result.pods_without_limits > 0
    assert result.budget.source is BudgetSource.DERIVED
    assert result.cpu_budget_used is not None
    # 46.25 reserved against a 64-core budget.
    assert result.cpu_budget_used == pytest.approx(46.25 / 64, abs=0.01)
    assert "arangodb-graphrag-retriever" in result.warning_services


def test_missing_metrics_leave_usage_unknown_not_zero() -> None:
    """A pod metrics-server has not scraped yet must not look 100% efficient."""
    raw = {
        "pods": fixture_items("pods"),
        "deployments": fixture_items("deployments"),
        "statefulsets": fixture_items("statefulsets"),
        "replicasets": fixture_items("replicasets"),
        "platform_services": fixture_items("arangoplatformservices"),
    }
    snapshot = assemble(raw, "ns", Settings(), usage={})
    report = rollup.namespace_report(snapshot)
    assert report.resources.usage.cpu_cores is None
    assert report.cpu_efficiency is None
    assert report.reclaimable_cpu_cores is None
    # And nothing can be called wasteful on the strength of unknown usage.
    assert rollup.waste(snapshot, Settings()) == []

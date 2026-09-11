"""The snapshot, asserted against the recorded fixtures.

These are the Phase 1 acceptance criteria from the plan, written as tests.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models.common import ProtectionLevel
from app.models.inventory import InventorySnapshot
from app.services.grouping import ARANGO_CLUSTER_KEY
from app.services.inventory import assemble, build_detail
from tests.conftest import fixture_items


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
    }
    return assemble(raw, "example-platform", Settings())


def test_every_pod_appears_exactly_once(snapshot: InventorySnapshot) -> None:
    assert len(snapshot.pods) == 59
    assert len({p.name for p in snapshot.pods}) == 59


def test_file_parser_rolls_up_four_workloads_and_32_pods(
    snapshot: InventorySnapshot,
) -> None:
    group = next(s for s in snapshot.services if s.name == "arangodb-file-parser")
    assert group.workload_count == 4
    assert group.pod_count == 32
    assert group.source == "ArangoPlatformService"

    workers = next(w for w in snapshot.workloads if w.name == "arangodb-file-parser-worker-pdf")
    assert workers.desired_replicas == 25
    assert workers.pod_count == 25
    assert workers.component == "worker-pdf"


def test_platform_ui_server_is_not_absorbed_into_platform_ui(
    snapshot: InventorySnapshot,
) -> None:
    ui = next(s for s in snapshot.services if s.name == "arangodb-platform-ui")
    server = next(s for s in snapshot.services if s.name == "arangodb-platform-ui-server")
    assert ui.instances == ["arangodb-platform-ui"]
    assert server.instances == ["arangodb-platform-ui-server"]


def test_retriever_satellites_group_under_one_service(
    snapshot: InventorySnapshot,
) -> None:
    group = next(s for s in snapshot.services if s.name == "arangodb-graphrag-retriever")
    assert len(group.instances) == 3
    assert all(i.startswith("arangodb-graphrag-retriever-") for i in group.instances)
    assert group.match_confidence == "instance"


def test_failing_service_names_the_failed_check(snapshot: InventorySnapshot) -> None:
    """Conditions say WHICH check failed, and carry their own messages."""
    group = next(s for s in snapshot.services if s.name == "arangodb-graphrag-retriever")
    assert group.ready is False
    failing = {c.type for c in group.conditions if not c.status}
    assert "ReleaseReady" in failing
    # The condition messages are generic ("Not ready") - useful for pinpointing
    # the failed check, useless as a diagnosis. Hence the next test.
    assert all(c.message for c in group.conditions)


def test_failing_service_explains_why_from_its_events(
    snapshot: InventorySnapshot,
) -> None:
    """The actual diagnosis lives in an event, not in a status condition.

    Without this, a user sees "ReleaseReady: False / Not ready" and still has to
    reach for kubectl - which is the thing this tool exists to avoid.
    """
    group = next(s for s in snapshot.services if s.name == "arangodb-graphrag-retriever")
    assert group.warning_count > 0
    assert group.latest_warning is not None
    assert "db_name is required" in group.latest_warning


def test_healthy_services_carry_no_warnings(snapshot: InventorySnapshot) -> None:
    healthy = next(s for s in snapshot.services if s.name == "arangodb-file-parser")
    assert healthy.warning_count == 0
    assert healthy.latest_warning is None


def test_unmanaged_workloads_still_appear(snapshot: InventorySnapshot) -> None:
    names = {s.name for s in snapshot.services}
    assert "operator" in names
    assert any(n.startswith("arangodb-autograph") for n in names)
    operator = next(s for s in snapshot.services if s.name == "operator")
    assert operator.source == "unmanaged"


def test_arango_cluster_is_synthetic_and_wholly_protected(
    snapshot: InventorySnapshot,
) -> None:
    group = next(s for s in snapshot.services if s.name == ARANGO_CLUSTER_KEY)
    assert group.source == "ArangoDeployment"
    assert group.pod_count == 12
    assert group.protection.level is ProtectionLevel.PROTECTED

    members = [w for w in snapshot.workloads if w.service == ARANGO_CLUSTER_KEY]
    tiers = {w.tier: w.desired_replicas for w in members}
    # Counts come from the ArangoDeployment spec, not from counting pods.
    assert tiers["agents"] == 3
    assert tiers["dbservers"] == 3
    assert tiers["coordinators"] == 3

    cluster_pods = [p for p in snapshot.pods if p.service == ARANGO_CLUSTER_KEY]
    assert len(cluster_pods) == 12
    assert all(p.protection.level is ProtectionLevel.PROTECTED for p in cluster_pods)
    assert all(p.protection.remediation for p in cluster_pods)


def test_the_operator_is_guarded_not_protected(snapshot: InventorySnapshot) -> None:
    """It is not operator-owned, but stopping it freezes every Arango resource."""
    workload = next(w for w in snapshot.workloads if w.name == "arango-operator-operator")
    assert workload.protection.level is ProtectionLevel.GUARDED
    assert workload.protection.reason


def test_ordinary_workloads_stay_actionable(snapshot: InventorySnapshot) -> None:
    workload = next(w for w in snapshot.workloads if w.name == "arangodb-file-parser-worker-pdf")
    assert workload.protection.level is ProtectionLevel.NORMAL


def test_reserved_totals_match_the_live_namespace(snapshot: InventorySnapshot) -> None:
    """46.25 cores and 128.4Gi reserved - the numbers the plan was built on."""
    total_cpu = 0.0
    total_mem = 0
    for pod in snapshot.pods:
        total_cpu += pod.resources.requests.cpu_cores or 0.0
        total_mem += pod.resources.requests.memory_bytes or 0
    assert total_cpu == pytest.approx(46.25, abs=0.01)
    assert total_mem / 1024**3 == pytest.approx(128.44, abs=0.05)


def test_containers_without_limits_are_counted_not_zeroed(
    snapshot: InventorySnapshot,
) -> None:
    unset = sum(p.resources.unset_limit_containers for p in snapshot.pods)
    assert unset > 0, "this namespace is known to have containers with no limits"


def test_uptime_is_numeric_and_sortable(snapshot: InventorySnapshot) -> None:
    running = [p for p in snapshot.pods if p.phase == "Running"]
    assert running
    assert all(isinstance(p.age_seconds, int) and p.age_seconds > 0 for p in running)
    # Sorting must work on the integer, never on a formatted string.
    ordered = sorted(running, key=lambda p: p.age_seconds or 0)
    assert ordered[0].age_seconds <= ordered[-1].age_seconds


def test_restarting_pod_keeps_pod_age_and_restart_count_separate(
    snapshot: InventorySnapshot,
) -> None:
    restarted = [p for p in snapshot.pods if p.restart_count > 0]
    assert restarted, "expected at least one pod with a restart"
    for pod in restarted:
        assert pod.last_restart_at is not None


def test_service_detail_carries_the_warnings_it_counts(
    snapshot: InventorySnapshot,
) -> None:
    """A count with no list behind it is worse than no count: the card promises
    an explanation the detail page then fails to give."""
    detail = build_detail(snapshot, "arangodb-graphrag-retriever")
    assert detail is not None
    assert detail.warning_count > 0
    assert detail.events, "warning_count was non-zero but no events were attached"
    assert any("db_name is required" in (e.message or "") for e in detail.events)


def test_warnings_are_capped_per_service(snapshot: InventorySnapshot) -> None:
    for events in snapshot.service_warnings.values():
        assert len(events) <= 20


def test_identical_warnings_collapse_into_one_counted_entry(
    snapshot: InventorySnapshot,
) -> None:
    """The failing install repeats one message hundreds of times. Rendering it
    hundreds of times buries every other warning and says nothing new."""
    events = snapshot.service_warnings["arangodb-graphrag-retriever"]
    seen = [(e.reason, e.message) for e in events]
    assert len(seen) == len(set(seen)), "identical warnings were not collapsed"
    # The count is preserved, so the scale of the problem is still visible.
    assert sum(e.count for e in events) > len(events)


def test_service_detail_carries_its_workloads_and_pods(
    snapshot: InventorySnapshot,
) -> None:
    detail = build_detail(snapshot, "arangodb-file-parser")
    assert detail is not None
    assert len(detail.workloads) == 4
    assert len(detail.pods) == 32
    assert build_detail(snapshot, "no-such-service") is None


def test_routes_are_attached_where_they_exist(snapshot: InventorySnapshot) -> None:
    with_routes = [s for s in snapshot.services if s.route_path]
    assert with_routes
    assert all(s.route_path and s.route_path.startswith("/") for s in with_routes)

"""The gates, the plans, and the things that must never happen.

Nothing here touches a cluster: planning is pure, and execution is exercised
against a fake client that records what it was asked to do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.models.actions import ActionType, BlockedReason, WorkloadTarget
from app.models.inventory import InventorySnapshot
from app.services import actions
from app.services.actions import ActionBlocked
from app.services.inventory import assemble
from app.store.state import StateStore
from tests.conftest import fixture_items

WORKER = "arangodb-file-parser-worker-default"
PDF_WORKER = "arangodb-file-parser-worker-pdf"
OPERATOR = "arango-operator-operator"


@pytest.fixture
def snapshot() -> InventorySnapshot:
    raw = {
        "pods": fixture_items("pods"),
        "deployments": fixture_items("deployments"),
        "statefulsets": fixture_items("statefulsets"),
        "replicasets": fixture_items("replicasets"),
        "platform_services": fixture_items("arangoplatformservices"),
        "arango_deployments": fixture_items("arangodeployments"),
    }
    return assemble(raw, "test-ns", Settings())


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "state.json")


class FakeClients:
    """Records calls instead of making them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.namespace = "test-ns"
        outer = self

        class Apps:
            def patch_namespaced_deployment_scale(
                self, name: str, ns: str, body: dict, **kwargs: Any
            ) -> None:
                outer.calls.append(("scale_deployment", {"name": name, "body": body, **kwargs}))

            def patch_namespaced_stateful_set_scale(
                self, name: str, ns: str, body: dict, **kwargs: Any
            ) -> None:
                outer.calls.append(("scale_sts", {"name": name, "body": body, **kwargs}))

            def patch_namespaced_deployment(
                self, name: str, ns: str, body: dict, **kwargs: Any
            ) -> None:
                outer.calls.append(("patch_deployment", {"name": name, "body": body, **kwargs}))

        class Core:
            def delete_namespaced_pod(self, name: str, ns: str, **kwargs: Any) -> None:
                outer.calls.append(("delete_pod", {"name": name, **kwargs}))

        self.apps = Apps()
        self.core = Core()


ENABLED = Settings(read_only=False)


# -- Gate 1: read-only ------------------------------------------------------


def test_read_only_blocks_every_action(snapshot: InventorySnapshot, store: StateStore) -> None:
    """The master switch. Nothing gets past it, whatever else is configured."""
    settings = Settings(read_only=True, allow_guarded_actions=True, allow_database_scaling=True)
    plan = actions.plan_scale(snapshot, settings, "Deployment", WORKER, 2)
    clients = FakeClients()

    with pytest.raises(ActionBlocked) as caught:
        actions.execute(clients, settings, store, plan, dry_run=False)  # type: ignore[arg-type]

    assert caught.value.reason is BlockedReason.READ_ONLY
    assert clients.calls == [], "read-only must not reach the API server at all"


def test_protection_is_reported_ahead_of_read_only(snapshot: InventorySnapshot) -> None:
    """Both refuse. Protection is the more useful answer: it is permanent and
    carries a remediation, while read-only is a setting someone can change."""
    settings = Settings(read_only=True)
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_scale(snapshot, settings, "ArangoDeployment", "dbserver", 1)
    assert caught.value.reason is BlockedReason.PROTECTED


def test_read_only_blocks_dry_runs_too(snapshot: InventorySnapshot, store: StateStore) -> None:
    # A dry run still issues a real API call, so it belongs behind the switch.
    plan = actions.plan_scale(snapshot, Settings(read_only=True), "Deployment", WORKER, 2)
    clients = FakeClients()
    with pytest.raises(ActionBlocked):
        actions.execute(clients, Settings(read_only=True), store, plan, dry_run=True)  # type: ignore[arg-type]
    assert clients.calls == []


# -- Gate 2: protected ------------------------------------------------------


@pytest.mark.parametrize("tier", ["agent", "dbserver", "coordinator"])
def test_operator_owned_workloads_are_refused(snapshot: InventorySnapshot, tier: str) -> None:
    """Scaling these through the core API is reconciled straight back, and
    scaling the database this way risks it. Refused regardless of config."""
    permissive = Settings(read_only=False, allow_guarded_actions=True)
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_scale(snapshot, permissive, "ArangoDeployment", tier, 1)

    assert caught.value.reason is BlockedReason.PROTECTED
    assert caught.value.remediation
    assert "Database page" in caught.value.remediation


def test_protected_pods_cannot_be_deleted(snapshot: InventorySnapshot) -> None:
    pod = next(p for p in snapshot.pods if p.service == "arangodb-cluster")
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_delete_pod(snapshot, Settings(read_only=False), pod.name)
    assert caught.value.reason is BlockedReason.PROTECTED


# -- Gate 3: guarded --------------------------------------------------------


def test_guarded_workloads_need_the_flag(snapshot: InventorySnapshot) -> None:
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_scale(snapshot, ENABLED, "Deployment", OPERATOR, 0)
    assert caught.value.reason is BlockedReason.GUARDED

    # With the flag set it plans normally.
    permissive = Settings(read_only=False, allow_guarded_actions=True)
    plan = actions.plan_scale(snapshot, permissive, "Deployment", OPERATOR, 0)
    assert plan.target_replicas == 0


# -- Planning ---------------------------------------------------------------


def test_scale_down_plan_names_what_it_kills(snapshot: InventorySnapshot) -> None:
    plan = actions.plan_scale(snapshot, ENABLED, "Deployment", WORKER, 2)
    assert plan.current_replicas == 5
    assert plan.target_replicas == 2
    assert len(plan.pods_terminating) == 3
    assert all(p.age_seconds is not None for p in plan.pods_terminating)
    # Reservations released, which is the number that matters for capacity.
    assert plan.frees.cpu_cores is not None
    assert plan.frees.cpu_cores == pytest.approx(2.25, abs=0.01)
    assert plan.requires_typed_confirmation is False


def test_stopping_requires_typed_confirmation_and_records_the_way_back(
    snapshot: InventorySnapshot,
) -> None:
    plan = actions.plan_scale(
        snapshot, ENABLED, "Deployment", PDF_WORKER, 0, action=ActionType.STOP
    )
    assert plan.target_replicas == 0
    assert plan.restore_to == 25
    assert plan.requires_typed_confirmation is True
    assert plan.warning and "stop serving" in plan.warning
    assert len(plan.pods_terminating) == 25
    assert plan.force is False
    assert plan.targets == []


def test_scaling_up_terminates_nothing(snapshot: InventorySnapshot) -> None:
    plan = actions.plan_scale(snapshot, ENABLED, "Deployment", WORKER, 8)
    assert plan.pods_terminating == []
    assert plan.frees.cpu_cores is None


def test_deleting_a_pod_says_it_frees_nothing(snapshot: InventorySnapshot) -> None:
    """The misunderstanding this tool most has to correct."""
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    plan = actions.plan_delete_pod(snapshot, ENABLED, pod.name)
    assert plan.warning is not None
    assert "frees nothing" in plan.warning
    assert "kill it instead" in plan.warning
    assert plan.frees.cpu_cores is None
    assert plan.force is False
    assert plan.targets == []


def test_force_deleting_a_pod_says_so(snapshot: InventorySnapshot) -> None:
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    plan = actions.plan_delete_pod(snapshot, ENABLED, pod.name, force=True)
    assert plan.force is True
    assert plan.warning and "force-deleted" in plan.warning


def test_killing_a_named_container_still_deletes_the_pod(snapshot: InventorySnapshot) -> None:
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    container = pod.containers[0]
    plan = actions.plan_delete_pod(snapshot, ENABLED, pod.name, force=True, container=container)
    assert container in (plan.warning or "")
    assert "cannot stop container" in (plan.warning or "")


def test_unknown_container_is_a_clean_404(snapshot: InventorySnapshot) -> None:
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_delete_pod(snapshot, ENABLED, pod.name, container="no-such-container")
    assert caught.value.reason is BlockedReason.NOT_FOUND


def test_kill_scales_to_zero_and_names_every_pod(snapshot: InventorySnapshot) -> None:
    plan = actions.plan_kill(snapshot, ENABLED, "Deployment", WORKER)
    assert plan.action is ActionType.KILL
    assert plan.target_replicas == 0
    assert plan.restore_to == 5
    assert plan.force is True
    assert plan.requires_typed_confirmation is True
    assert len(plan.pods_terminating) == 5
    assert plan.targets == [WorkloadTarget(kind="Deployment", name=WORKER, current_replicas=5)]
    assert plan.warning and "force-deleted" in plan.warning


def test_kill_service_covers_every_actionable_workload(snapshot: InventorySnapshot) -> None:
    plan = actions.plan_kill_service(snapshot, ENABLED, "arangodb-file-parser")
    assert plan.action is ActionType.KILL_SERVICE
    assert plan.target_replicas == 0
    assert plan.requires_typed_confirmation is True
    assert {t.name for t in plan.targets} == {
        "arangodb-file-parser-api",
        "arangodb-file-parser-orchestrator",
        "arangodb-file-parser-worker-default",
        "arangodb-file-parser-worker-pdf",
    }
    assert len(plan.pods_terminating) == 32


def test_kill_service_refuses_the_database(snapshot: InventorySnapshot) -> None:
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_kill_service(snapshot, ENABLED, "arangodb-cluster")
    assert caught.value.reason is BlockedReason.PROTECTED


def test_kill_after_scale_to_zero_still_deletes_leftover_pods(
    snapshot: InventorySnapshot,
) -> None:
    workload = next(w for w in snapshot.workloads if w.name == WORKER)
    workload.desired_replicas = 0
    plan = actions.plan_kill(snapshot, ENABLED, "Deployment", WORKER)
    assert plan.restore_to is None
    assert plan.requires_typed_confirmation is False
    assert len(plan.pods_terminating) == 5
    assert plan.warning and "already 0" in plan.warning


def test_deleting_a_leftover_pod_after_scale_to_zero_is_permanent(
    snapshot: InventorySnapshot,
) -> None:
    workload = next(w for w in snapshot.workloads if w.name == WORKER)
    workload.desired_replicas = 0
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    plan = actions.plan_delete_pod(snapshot, ENABLED, pod.name, force=True)
    assert plan.warning is not None
    assert "will not be replaced" in plan.warning
    assert "frees nothing" not in plan.warning
    assert plan.frees.cpu_cores is not None


def test_kill_guarded_workload_needs_the_flag(snapshot: InventorySnapshot) -> None:
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_kill(snapshot, ENABLED, "Deployment", OPERATOR)
    assert caught.value.reason is BlockedReason.GUARDED


def test_restart_replaces_pods_without_changing_the_count(
    snapshot: InventorySnapshot,
) -> None:
    plan = actions.plan_restart(snapshot, ENABLED, "Deployment", WORKER)
    assert plan.current_replicas == plan.target_replicas == 5
    assert plan.requires_typed_confirmation is False


def test_unknown_workload_is_a_clean_404(snapshot: InventorySnapshot) -> None:
    with pytest.raises(ActionBlocked) as caught:
        actions.plan_scale(snapshot, ENABLED, "Deployment", "no-such-thing", 1)
    assert caught.value.reason is BlockedReason.NOT_FOUND


# -- Restore ----------------------------------------------------------------


def test_restore_uses_the_recorded_count(snapshot: InventorySnapshot, store: StateStore) -> None:
    store.record_stop("test-ns", "Deployment", WORKER, 5, "someone")
    plan = actions.plan_restore(snapshot, ENABLED, store, "Deployment", WORKER)
    assert plan.target_replicas == 5
    assert plan.warning is None


def test_restore_never_invents_a_count(snapshot: InventorySnapshot, store: StateStore) -> None:
    """If this tool did not stop it, it does not know what "before" was."""
    plan = actions.plan_restore(snapshot, ENABLED, store, "Deployment", WORKER)
    assert plan.target_replicas == 1
    assert plan.warning is not None
    assert "no record" in plan.warning


# -- Execution --------------------------------------------------------------


def test_dry_run_sends_dry_run_all_and_changes_nothing(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    """The dry run is a real, authorised, non-persisting API call - not a
    client-side guess - so an RBAC gap surfaces before the user confirms."""
    plan = actions.plan_scale(snapshot, ENABLED, "Deployment", WORKER, 2)
    clients = FakeClients()
    result = actions.execute(clients, ENABLED, store, plan, dry_run=True)  # type: ignore[arg-type]

    assert result.executed is False
    assert result.plan and result.plan.server_dry_run == "accepted"
    call, kwargs = clients.calls[0]
    assert call == "scale_deployment"
    assert kwargs["dry_run"] == "All"
    assert store.history() == [], "a dry run must not be logged as an action"


def test_real_scale_omits_dry_run_and_is_logged(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    plan = actions.plan_scale(snapshot, ENABLED, "Deployment", WORKER, 2)
    clients = FakeClients()
    result = actions.execute(clients, ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]

    assert result.executed is True
    _, kwargs = clients.calls[0]
    assert "dry_run" not in kwargs
    assert kwargs["body"] == {"spec": {"replicas": 2}}

    entry = store.history()[0]
    assert entry["action"] == "scale"
    assert entry["from_replicas"] == 5
    assert entry["to_replicas"] == 2


def test_stop_records_the_previous_count_before_patching(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    """Written first, so a crash mid-action still leaves a way back."""
    plan = actions.plan_scale(
        snapshot, ENABLED, "Deployment", PDF_WORKER, 0, action=ActionType.STOP
    )
    actions.execute(FakeClients(), ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]

    record = store.get_stop("test-ns", "Deployment", PDF_WORKER)
    assert record is not None
    assert record["previous_replicas"] == 25


def test_dry_run_stop_records_nothing(snapshot: InventorySnapshot, store: StateStore) -> None:
    plan = actions.plan_scale(
        snapshot, ENABLED, "Deployment", PDF_WORKER, 0, action=ActionType.STOP
    )
    actions.execute(FakeClients(), ENABLED, store, plan, dry_run=True)  # type: ignore[arg-type]
    assert store.get_stop("test-ns", "Deployment", PDF_WORKER) is None


def test_restore_clears_the_record(snapshot: InventorySnapshot, store: StateStore) -> None:
    store.record_stop("test-ns", "Deployment", WORKER, 5, "someone")
    plan = actions.plan_restore(snapshot, ENABLED, store, "Deployment", WORKER)
    actions.execute(FakeClients(), ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]
    assert store.get_stop("test-ns", "Deployment", WORKER) is None


def test_restart_patches_the_pod_template_annotation(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    plan = actions.plan_restart(snapshot, ENABLED, "Deployment", WORKER)
    clients = FakeClients()
    actions.execute(clients, ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]

    call, kwargs = clients.calls[0]
    assert call == "patch_deployment"
    annotations = kwargs["body"]["spec"]["template"]["metadata"]["annotations"]
    assert "kubectl.kubernetes.io/restartedAt" in annotations


def test_statefulsets_use_the_statefulset_endpoint(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    sts = next(w for w in snapshot.workloads if w.kind == "StatefulSet")
    plan = actions.plan_scale(snapshot, ENABLED, "StatefulSet", sts.name, 0)
    clients = FakeClients()
    actions.execute(clients, ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]
    assert clients.calls[0][0] == "scale_sts"


def test_delete_pod_uses_graceful_period_unless_forced(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    clients = FakeClients()
    actions.execute(
        clients,
        ENABLED,
        store,
        actions.plan_delete_pod(snapshot, ENABLED, pod.name),
        dry_run=False,
    )  # type: ignore[arg-type]
    assert clients.calls[0][0] == "delete_pod"
    assert clients.calls[0][1]["grace_period_seconds"] == 30
    assert "dry_run" not in clients.calls[0][1]


def test_force_delete_pod_uses_grace_zero(snapshot: InventorySnapshot, store: StateStore) -> None:
    pod = next(p for p in snapshot.pods if p.workload and p.workload.name == WORKER)
    clients = FakeClients()
    actions.execute(
        clients,
        ENABLED,
        store,
        actions.plan_delete_pod(snapshot, ENABLED, pod.name, force=True),
        dry_run=False,
    )  # type: ignore[arg-type]
    assert clients.calls[0][1]["grace_period_seconds"] == 0


def test_kill_records_the_count_then_force_deletes_pods(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    plan = actions.plan_kill(snapshot, ENABLED, "Deployment", WORKER)
    clients = FakeClients()
    actions.execute(clients, ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]

    kinds = [call for call, _ in clients.calls]
    assert kinds[0] == "scale_deployment"
    deletes = [kwargs for call, kwargs in clients.calls if call == "delete_pod"]
    assert len(deletes) == 5
    assert all(item["grace_period_seconds"] == 0 for item in deletes)
    assert clients.calls[0][1]["body"] == {"spec": {"replicas": 0}}

    record = store.get_stop("test-ns", "Deployment", WORKER)
    assert record is not None
    assert record["previous_replicas"] == 5


def test_dry_run_kill_records_nothing_and_marks_every_call(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    plan = actions.plan_kill(snapshot, ENABLED, "Deployment", WORKER)
    clients = FakeClients()
    result = actions.execute(clients, ENABLED, store, plan, dry_run=True)  # type: ignore[arg-type]

    assert result.executed is False
    assert result.plan and result.plan.server_dry_run == "accepted"
    assert all(kwargs.get("dry_run") == "All" for _, kwargs in clients.calls)
    assert store.get_stop("test-ns", "Deployment", WORKER) is None
    assert store.history() == []


def test_kill_service_scales_each_workload_then_deletes_pods(
    snapshot: InventorySnapshot, store: StateStore
) -> None:
    plan = actions.plan_kill_service(snapshot, ENABLED, "arangodb-file-parser")
    clients = FakeClients()
    actions.execute(clients, ENABLED, store, plan, dry_run=False)  # type: ignore[arg-type]

    scales = [kwargs for call, kwargs in clients.calls if call == "scale_deployment"]
    deletes = [kwargs for call, kwargs in clients.calls if call == "delete_pod"]
    assert len(scales) == 4
    assert len(deletes) == 32
    assert all(item["body"] == {"spec": {"replicas": 0}} for item in scales)
    assert store.get_stop("test-ns", "Deployment", PDF_WORKER) is not None
    assert store.get_stop("test-ns", "Deployment", WORKER) is not None

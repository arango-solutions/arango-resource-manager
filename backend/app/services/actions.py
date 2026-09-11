"""Mutating actions, and the gates every one of them passes through.

Two-phase throughout: a plan is computed first and returned with the result,
even on a real run, so what happened is always described in the same terms the
user confirmed.

Three gates. All three refuse, and all are enforced here rather than in the
UI - a disabled button is a courtesy, this is the control, and it holds
against a hand-rolled curl.

  protection == PROTECTED - operator-owned. Refused regardless of any config.
  protection == GUARDED   - needs ARM_ALLOW_GUARDED_ACTIONS.
  ARM_READ_ONLY           - the master switch, refuses everything.

The protection gates run while planning and the read-only switch runs at
execution, so a protected workload on a read-only instance reports "protected"
rather than "read-only". That is deliberate: protection is a permanent fact
about the workload with a real remediation attached, while read-only is a
setting someone can change, and the permanent reason is the more useful
answer. Planning is pure and touches nothing, so nothing escapes by running
first.

The dry run is not a simulation. It issues the real patch with dryRun=All, so
the API server validates and authorises it without persisting - which surfaces
an RBAC gap or an admission webhook rejection *before* the user is asked to
type a workload name to confirm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from kubernetes.client.exceptions import ApiException

from app.config import Settings
from app.k8s.client import KubeClients
from app.models.actions import (
    ActionPlan,
    ActionResult,
    ActionType,
    BlockedReason,
    TerminatingPod,
)
from app.models.common import ProtectionLevel, Resources
from app.models.inventory import InventorySnapshot, PodSummary, WorkloadSummary
from app.services import inventory as inventory_service
from app.services.quantities import add_optional
from app.store.state import StateStore

log = structlog.get_logger(__name__)

_TIMEOUT = 30
ACTOR = "arango-resource-manager"


class ActionBlocked(Exception):
    """An action refused by a gate. Carries what to tell the user instead."""

    def __init__(self, reason: BlockedReason, detail: str, remediation: str | None = None) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.remediation = remediation


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------


def _check_read_only(settings: Settings) -> None:
    if settings.read_only:
        raise ActionBlocked(
            BlockedReason.READ_ONLY,
            "This instance is read-only.",
            "Set ARM_READ_ONLY=false where the API is started to enable actions.",
        )


def _check_protection(workload: WorkloadSummary, settings: Settings) -> None:
    level = workload.protection.level
    if level is ProtectionLevel.PROTECTED:
        raise ActionBlocked(
            BlockedReason.PROTECTED,
            workload.protection.reason or "This workload is managed by an operator.",
            workload.protection.remediation,
        )
    if level is ProtectionLevel.GUARDED and not settings.allow_guarded_actions:
        raise ActionBlocked(
            BlockedReason.GUARDED,
            workload.protection.reason or "This is platform infrastructure.",
            workload.protection.remediation or "Set ARM_ALLOW_GUARDED_ACTIONS=true to act on it.",
        )


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


def find_workload(snapshot: InventorySnapshot, kind: str, name: str) -> WorkloadSummary:
    workload = next((w for w in snapshot.workloads if w.kind == kind and w.name == name), None)
    if workload is None:
        raise ActionBlocked(BlockedReason.NOT_FOUND, f"No {kind} named {name!r}.")
    return workload


def _pods_of(snapshot: InventorySnapshot, workload: WorkloadSummary) -> list[PodSummary]:
    return [
        pod
        for pod in snapshot.pods
        if pod.workload
        and pod.workload.kind == workload.kind
        and pod.workload.name == workload.name
    ]


def _freed_by(pods: list[PodSummary]) -> Resources:
    """Reservations released when these pods go away."""
    cpu: float | None = None
    memory: float | None = None
    for pod in pods:
        cpu = add_optional(cpu, pod.resources.requests.cpu_cores)
        memory = add_optional(
            memory,
            None
            if pod.resources.requests.memory_bytes is None
            else float(pod.resources.requests.memory_bytes),
        )
    return Resources(cpu_cores=cpu, memory_bytes=None if memory is None else int(memory))


def _victims(pods: list[PodSummary], current: int, target: int) -> list[PodSummary]:
    """Which pods a scale-down would terminate.

    Kubernetes picks by its own ordering, so this is indicative. Youngest first
    matches the common case and, more importantly, shows the user the shape of
    what they are about to lose rather than a bare count.
    """
    if target >= current:
        return []
    ordered = sorted(pods, key=lambda pod: pod.age_seconds or 0)
    return ordered[: current - target]


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def plan_scale(
    snapshot: InventorySnapshot,
    settings: Settings,
    kind: str,
    name: str,
    replicas: int,
    action: ActionType = ActionType.SCALE,
) -> ActionPlan:
    workload = find_workload(snapshot, kind, name)
    _check_protection(workload, settings)

    pods = _pods_of(snapshot, workload)
    current = workload.desired_replicas
    terminating = _victims(pods, current, replicas)

    return ActionPlan(
        action=action,
        kind=kind,
        name=name,
        namespace=snapshot.namespace,
        current_replicas=current,
        target_replicas=replicas,
        pods_terminating=[
            TerminatingPod(name=pod.name, age_seconds=pod.age_seconds) for pod in terminating
        ],
        frees=_freed_by(terminating),
        restore_to=current if replicas == 0 and current > 0 else None,
        protection=workload.protection,
        # Taking a service to zero makes it start refusing requests. Anything
        # less is reversible in a way the user can see immediately.
        requires_typed_confirmation=replicas == 0 and current > 0,
        warning=(
            "This service will stop serving requests until it is restored."
            if replicas == 0 and current > 0
            else None
        ),
    )


def plan_restore(
    snapshot: InventorySnapshot, settings: Settings, store: StateStore, kind: str, name: str
) -> ActionPlan:
    workload = find_workload(snapshot, kind, name)
    _check_protection(workload, settings)

    record = store.get_stop(snapshot.namespace, kind, name)
    if record is not None:
        target = int(record["previous_replicas"])
        warning = None
    else:
        # Never invent a replica count. If this tool did not stop it, it does
        # not know what "before" was, and says so.
        target = 1
        warning = (
            "This tool has no record of stopping this workload, so it does not "
            "know the previous replica count. Restoring will set it to 1."
        )

    return ActionPlan(
        action=ActionType.RESTORE,
        kind=kind,
        name=name,
        namespace=snapshot.namespace,
        current_replicas=workload.desired_replicas,
        target_replicas=target,
        restore_to=target,
        protection=workload.protection,
        warning=warning,
    )


def plan_restart(
    snapshot: InventorySnapshot, settings: Settings, kind: str, name: str
) -> ActionPlan:
    workload = find_workload(snapshot, kind, name)
    _check_protection(workload, settings)
    pods = _pods_of(snapshot, workload)

    return ActionPlan(
        action=ActionType.RESTART,
        kind=kind,
        name=name,
        namespace=snapshot.namespace,
        current_replicas=workload.desired_replicas,
        target_replicas=workload.desired_replicas,
        pods_terminating=[
            TerminatingPod(name=pod.name, age_seconds=pod.age_seconds) for pod in pods
        ],
        protection=workload.protection,
        warning="Pods are replaced gradually; the rollout strategy decides how many at a time.",
    )


def plan_delete_pod(snapshot: InventorySnapshot, settings: Settings, pod_name: str) -> ActionPlan:
    pod = next((p for p in snapshot.pods if p.name == pod_name), None)
    if pod is None:
        raise ActionBlocked(BlockedReason.NOT_FOUND, f"No pod named {pod_name!r}.")

    if pod.protection.level is ProtectionLevel.PROTECTED:
        raise ActionBlocked(
            BlockedReason.PROTECTED,
            pod.protection.reason or "This pod is managed by an operator.",
            pod.protection.remediation,
        )
    if pod.protection.level is ProtectionLevel.GUARDED and not settings.allow_guarded_actions:
        raise ActionBlocked(
            BlockedReason.GUARDED,
            pod.protection.reason or "This pod belongs to platform infrastructure.",
            "Set ARM_ALLOW_GUARDED_ACTIONS=true to act on it.",
        )

    controlled = pod.workload is not None
    return ActionPlan(
        action=ActionType.DELETE_POD,
        kind="Pod",
        name=pod_name,
        namespace=snapshot.namespace,
        pods_terminating=[TerminatingPod(name=pod.name, age_seconds=pod.age_seconds)],
        frees=_freed_by([pod]) if not controlled else Resources(),
        protection=pod.protection,
        warning=(
            # The single most common misunderstanding this tool has to correct.
            f"This frees nothing. {pod.workload.kind} "
            f"{pod.workload.name} will replace this pod within seconds. "
            "To actually stop the service, scale it to 0 instead."
            if pod.workload
            else "This pod has no controller, so deleting it is permanent."
        ),
    )


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def _scale(clients: KubeClients, kind: str, name: str, replicas: int, dry_run: bool) -> None:
    body = {"spec": {"replicas": replicas}}
    kwargs: dict[str, Any] = {"_request_timeout": _TIMEOUT}
    if dry_run:
        kwargs["dry_run"] = "All"

    if kind == "StatefulSet":
        clients.apps.patch_namespaced_stateful_set_scale(name, clients.namespace, body, **kwargs)
    else:
        clients.apps.patch_namespaced_deployment_scale(name, clients.namespace, body, **kwargs)


def _restart(clients: KubeClients, kind: str, name: str, dry_run: bool) -> None:
    # Identical to `kubectl rollout restart`: touching the pod template
    # annotation makes the controller roll new pods.
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": datetime.now(UTC).isoformat()
                    }
                }
            }
        }
    }
    kwargs: dict[str, Any] = {"_request_timeout": _TIMEOUT}
    if dry_run:
        kwargs["dry_run"] = "All"

    if kind == "StatefulSet":
        clients.apps.patch_namespaced_stateful_set(name, clients.namespace, body, **kwargs)
    else:
        clients.apps.patch_namespaced_deployment(name, clients.namespace, body, **kwargs)


def _delete_pod(clients: KubeClients, name: str, dry_run: bool) -> None:
    kwargs: dict[str, Any] = {"grace_period_seconds": 30, "_request_timeout": _TIMEOUT}
    if dry_run:
        kwargs["dry_run"] = "All"
    clients.core.delete_namespaced_pod(name, clients.namespace, **kwargs)


def execute(
    clients: KubeClients,
    settings: Settings,
    store: StateStore,
    plan: ActionPlan,
    dry_run: bool,
) -> ActionResult:
    """Run a plan, or validate it against the API server without persisting."""
    _check_read_only(settings)

    try:
        if plan.action in (ActionType.SCALE, ActionType.STOP, ActionType.RESTORE):
            target = plan.target_replicas or 0
            # The record goes in before the patch: if this process dies
            # mid-action, the way back still exists.
            if not dry_run and plan.action is ActionType.STOP and plan.restore_to:
                store.record_stop(plan.namespace, plan.kind, plan.name, plan.restore_to, ACTOR)
            _scale(clients, plan.kind, plan.name, target, dry_run)
            if not dry_run and plan.action is ActionType.RESTORE:
                store.clear_stop(plan.namespace, plan.kind, plan.name)

        elif plan.action is ActionType.RESTART:
            _restart(clients, plan.kind, plan.name, dry_run)

        elif plan.action is ActionType.DELETE_POD:
            _delete_pod(clients, plan.name, dry_run)

    except ApiException as exc:
        detail = f"The API server rejected this: {exc.status} {exc.reason}."
        log.warning("action.rejected", action=plan.action, name=plan.name, status=exc.status)
        if not dry_run:
            store.append_history(
                {
                    "action": plan.action,
                    "kind": plan.kind,
                    "name": plan.name,
                    "from_replicas": plan.current_replicas,
                    "to_replicas": plan.target_replicas,
                    "dry_run": False,
                    "result": "error",
                    "detail": detail,
                }
            )
        raise ActionBlocked(BlockedReason.INVALID, detail) from exc

    if dry_run:
        plan.server_dry_run = "accepted"
        return ActionResult(executed=False, dry_run=True, plan=plan)

    store.append_history(
        {
            "action": plan.action,
            "kind": plan.kind,
            "name": plan.name,
            "from_replicas": plan.current_replicas,
            "to_replicas": plan.target_replicas,
            "dry_run": False,
            "result": "ok",
        }
    )
    # The next read must show the effect of what just happened, not a snapshot
    # from before it.
    inventory_service.invalidate()
    log.info("action.executed", action=plan.action, kind=plan.kind, name=plan.name)
    return ActionResult(executed=True, dry_run=False, plan=plan)

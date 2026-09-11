"""Resizing the ArangoDB cluster the correct way.

Protection refuses core-API scaling of cluster members because the operator
reconciles it straight back. This is the path that actually works: patch the
ArangoDeployment spec and let the operator converge.

The per-tier rules are domain knowledge, not plumbing, and the API enforces
them rather than trusting the UI to:

  coordinators  stateless query routers - scale freely
  gateways      stateless - scale freely
  dbservers     scale UP freely. Scaling DOWN makes the operator drain shards
                off the departing server, which is slow and fails outright if
                the replication factor cannot be satisfied afterwards
  agents        never. The agency is a RAFT quorum; changing its size after
                creation is unsupported by the operator and risks the cluster

Agents are refused here regardless of configuration. There is no flag for it,
because there is no good reason to do it from a dashboard.
"""

from __future__ import annotations

from typing import Any

import structlog
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field

from app.config import Settings
from app.k8s.client import ARANGO_CRS, KubeClients
from app.models.actions import ActionPlan, ActionType, BlockedReason
from app.models.inventory import Condition
from app.services.actions import ActionBlocked
from app.services.grouping import conditions_of, name_of
from app.services.inventory import get_snapshot

log = structlog.get_logger(__name__)

_TIMEOUT = 30
_GROUP, _VERSION, _PLURAL = ARANGO_CRS["ArangoDeployment"]

SCALABLE_TIERS = ("coordinators", "gateways", "dbservers")
IMMUTABLE_TIERS = ("agents",)

TIER_POLICY: dict[str, str] = {
    "coordinators": "free",
    "gateways": "free",
    "dbservers": "drain-on-shrink",
    "agents": "immutable",
}

MIN_COUNTS: dict[str, int] = {
    # Below these the cluster loses redundancy or stops serving entirely.
    "coordinators": 1,
    "gateways": 1,
    "dbservers": 1,
}


class Tier(BaseModel):
    name: str
    count: int
    ready: int = 0
    policy: str
    scalable: bool
    note: str


class DatabaseStatus(BaseModel):
    name: str
    mode: str | None = None
    ready: bool | None = None
    scaling_enabled: bool
    tiers: list[Tier] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)


_NOTES = {
    "coordinators": "Stateless query routers. Safe to scale in either direction.",
    "gateways": "Stateless. Safe to scale in either direction.",
    "dbservers": (
        "Scaling up is safe. Scaling down makes the operator move shards off the "
        "departing server first, which takes time and fails if the replication "
        "factor cannot still be met."
    ),
    "agents": (
        "The agency is a RAFT quorum. Changing the agent count after the cluster "
        "was created is unsupported by the operator and risks the whole database."
    ),
}


def fetch(clients: KubeClients) -> dict[str, Any]:
    try:
        items = clients.custom.list_namespaced_custom_object(
            group=_GROUP,
            version=_VERSION,
            namespace=clients.namespace,
            plural=_PLURAL,
            _request_timeout=_TIMEOUT,
        ).get("items", [])
    except ApiException as exc:
        raise ActionBlocked(
            BlockedReason.NOT_FOUND, f"Could not read the ArangoDeployment: {exc.status}."
        ) from exc

    if not items:
        raise ActionBlocked(
            BlockedReason.NOT_FOUND, "There is no ArangoDeployment in this namespace."
        )
    return dict(items[0])


def status(clients: KubeClients, settings: Settings) -> DatabaseStatus:
    deployment = fetch(clients)
    spec = deployment.get("spec", {}) or {}
    snapshot = get_snapshot(clients)

    ready_by_tier = {
        workload.tier: workload.ready_replicas for workload in snapshot.workloads if workload.tier
    }

    tiers = [
        Tier(
            name=tier,
            count=int((spec.get(tier) or {}).get("count") or 0),
            ready=ready_by_tier.get(tier, 0),
            policy=TIER_POLICY[tier],
            scalable=tier in SCALABLE_TIERS and settings.allow_database_scaling,
            note=_NOTES[tier],
        )
        for tier in (*SCALABLE_TIERS, *IMMUTABLE_TIERS)
        if tier in spec
    ]

    conditions = [Condition(**c) for c in conditions_of(deployment)]
    return DatabaseStatus(
        name=name_of(deployment),
        mode=spec.get("mode"),
        ready=next((c.status for c in conditions if c.type == "Ready"), None),
        scaling_enabled=settings.allow_database_scaling,
        tiers=sorted(tiers, key=lambda t: t.name),
        conditions=conditions,
    )


def plan_scale(clients: KubeClients, settings: Settings, tier: str, count: int) -> ActionPlan:
    if tier in IMMUTABLE_TIERS:
        raise ActionBlocked(
            BlockedReason.TIER_IMMUTABLE,
            f"The {tier} count cannot be changed after the cluster was created.",
            _NOTES[tier],
        )
    if tier not in SCALABLE_TIERS:
        raise ActionBlocked(BlockedReason.INVALID, f"{tier!r} is not a scalable tier.")

    minimum = MIN_COUNTS.get(tier, 1)
    if count < minimum:
        raise ActionBlocked(
            BlockedReason.INVALID,
            f"{tier} cannot go below {minimum}; the cluster would stop serving.",
        )

    deployment = fetch(clients)
    current = int((deployment.get("spec", {}).get(tier) or {}).get("count") or 0)
    shrinking = count < current

    return ActionPlan(
        action=ActionType.DATABASE_SCALE,
        kind="ArangoDeployment",
        name=f"{name_of(deployment)}/{tier}",
        namespace=clients.namespace,
        current_replicas=current,
        target_replicas=count,
        # Shrinking dbservers moves data. That deserves the same friction as
        # taking a service to zero.
        requires_typed_confirmation=shrinking and tier == "dbservers",
        warning=(
            _NOTES["dbservers"]
            if shrinking and tier == "dbservers"
            else ("Removing a stateless member." if shrinking else None)
        ),
    )


def execute(
    clients: KubeClients, settings: Settings, plan: ActionPlan, tier: str, dry_run: bool
) -> ActionPlan:
    if settings.read_only:
        raise ActionBlocked(
            BlockedReason.READ_ONLY,
            "This instance is read-only.",
            "Set ARM_READ_ONLY=false where the API is started.",
        )
    if not settings.allow_database_scaling:
        raise ActionBlocked(
            BlockedReason.DATABASE_LOCKED,
            "Resizing the database is disabled.",
            "Set ARM_ALLOW_DATABASE_SCALING=true where the API is started.",
        )

    body = {"spec": {tier: {"count": plan.target_replicas}}}
    kwargs: dict[str, Any] = {"_request_timeout": _TIMEOUT}
    if dry_run:
        kwargs["dry_run"] = "All"

    deployment_name = plan.name.split("/")[0]
    try:
        clients.custom.patch_namespaced_custom_object(
            group=_GROUP,
            version=_VERSION,
            namespace=clients.namespace,
            plural=_PLURAL,
            name=deployment_name,
            body=body,
            **kwargs,
        )
    except ApiException as exc:
        raise ActionBlocked(
            BlockedReason.INVALID,
            f"The operator rejected this: {exc.status} {exc.reason}.",
        ) from exc

    if dry_run:
        plan.server_dry_run = "accepted"
    else:
        log.info("database.scaled", tier=tier, to=plan.target_replicas)
    return plan

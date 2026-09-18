"""Action requests, plans and results."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Protection, Resources


class ActionType(StrEnum):
    SCALE = "scale"
    STOP = "stop"
    RESTORE = "restore"
    RESTART = "restart"
    DELETE_POD = "delete_pod"
    KILL = "kill"
    KILL_SERVICE = "kill_service"
    DATABASE_SCALE = "database_scale"


class BlockedReason(StrEnum):
    READ_ONLY = "read_only"
    PROTECTED = "protected"
    GUARDED = "guarded"
    DATABASE_LOCKED = "database_locked"
    TIER_IMMUTABLE = "tier_immutable"
    NOT_FOUND = "not_found"
    INVALID = "invalid"


class TerminatingPod(BaseModel):
    name: str
    age_seconds: int | None = None


class WorkloadTarget(BaseModel):
    """One workload a multi-target action (kill, kill-service) will touch."""

    kind: str
    name: str
    current_replicas: int = 0


class ActionPlan(BaseModel):
    """What an action would do, computed before it is offered for confirmation."""

    action: ActionType
    kind: str
    name: str
    namespace: str

    current_replicas: int | None = None
    target_replicas: int | None = None

    pods_terminating: list[TerminatingPod] = Field(default_factory=list)
    frees: Resources = Field(default_factory=Resources)
    """Reservations released. Reserved, not used - stopping something frees what
    it held from the scheduler, whether or not it was using it."""

    restore_to: int | None = None
    protection: Protection = Field(default_factory=Protection)
    server_dry_run: str | None = None
    """"accepted" when the API server validated and authorised the real patch."""

    requires_typed_confirmation: bool = False
    warning: str | None = None
    force: bool = False
    """True when pods are deleted with gracePeriodSeconds=0."""
    targets: list[WorkloadTarget] = Field(default_factory=list)
    """Workloads a kill/kill-service plan will scale. Empty for single-object actions."""


class ActionResult(BaseModel):
    executed: bool
    dry_run: bool
    plan: ActionPlan | None = None
    blocked_reason: BlockedReason | None = None
    detail: str | None = None
    remediation: str | None = None


class ScaleRequest(BaseModel):
    kind: str = "Deployment"
    name: str
    replicas: int = Field(ge=0, le=500)
    dry_run: bool = True


class WorkloadRequest(BaseModel):
    kind: str = "Deployment"
    name: str
    dry_run: bool = True


class PodDeleteRequest(BaseModel):
    dry_run: bool = True
    force: bool = False
    container: str | None = None
    """Named only so the plan can say which container the user pointed at.
    Kubernetes cannot stop one container; the pod is what gets deleted."""


class ServiceKillRequest(BaseModel):
    dry_run: bool = True


class DatabaseScaleRequest(BaseModel):
    tier: str
    count: int = Field(ge=0, le=64)
    dry_run: bool = True


class ActionRecord(BaseModel):
    ts: str
    action: str
    kind: str | None = None
    name: str | None = None
    from_replicas: int | None = None
    to_replicas: int | None = None
    dry_run: bool = False
    result: str = "ok"
    detail: str | None = None

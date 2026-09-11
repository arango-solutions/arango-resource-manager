"""Shared model types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.services.quantities import add_optional


class ProtectionLevel(StrEnum):
    """How far this tool may go when acting on a workload."""

    PROTECTED = "protected"
    """Owned by an operator. Core Kubernetes mutations are refused outright."""

    GUARDED = "guarded"
    """Platform infrastructure. Needs an extra config flag and a typed confirm."""

    NORMAL = "normal"


class Protection(BaseModel):
    level: ProtectionLevel = ProtectionLevel.NORMAL
    reason: str | None = None
    remediation: str | None = None

    @property
    def actionable(self) -> bool:
        return self.level is not ProtectionLevel.NORMAL


class Resources(BaseModel):
    """A CPU/memory pair where None means "not set", distinct from zero."""

    cpu_cores: float | None = None
    memory_bytes: int | None = None

    def __add__(self, other: Resources) -> Resources:
        return Resources(
            cpu_cores=add_optional(self.cpu_cores, other.cpu_cores),
            memory_bytes=_add_int(self.memory_bytes, other.memory_bytes),
        )

    @property
    def is_set(self) -> bool:
        return self.cpu_cores is not None or self.memory_bytes is not None


def _add_int(left: int | None, right: int | None) -> int | None:
    total = add_optional(
        None if left is None else float(left),
        None if right is None else float(right),
    )
    return None if total is None else int(total)


class ResourceTriple(BaseModel):
    """What a thing uses, what it reserved, and what it may burst to."""

    usage: Resources = Field(default_factory=Resources)
    requests: Resources = Field(default_factory=Resources)
    limits: Resources = Field(default_factory=Resources)

    unset_request_containers: int = 0
    unset_limit_containers: int = 0
    container_count: int = 0

    def __add__(self, other: ResourceTriple) -> ResourceTriple:
        return ResourceTriple(
            usage=self.usage + other.usage,
            requests=self.requests + other.requests,
            limits=self.limits + other.limits,
            unset_request_containers=self.unset_request_containers + other.unset_request_containers,
            unset_limit_containers=self.unset_limit_containers + other.unset_limit_containers,
            container_count=self.container_count + other.container_count,
        )

    @property
    def cpu_efficiency(self) -> float | None:
        """Usage as a fraction of what was reserved. None when either is unknown."""
        used, reserved = self.usage.cpu_cores, self.requests.cpu_cores
        if used is None or not reserved:
            return None
        return used / reserved

    @property
    def memory_efficiency(self) -> float | None:
        used, reserved = self.usage.memory_bytes, self.requests.memory_bytes
        if used is None or not reserved:
            return None
        return used / reserved

    @property
    def reclaimable_cpu_cores(self) -> float | None:
        """Reserved but unused CPU - the number this whole app exists to surface."""
        used, reserved = self.usage.cpu_cores, self.requests.cpu_cores
        if used is None or reserved is None:
            return None
        return max(0.0, reserved - used)

    @property
    def reclaimable_memory_bytes(self) -> int | None:
        used, reserved = self.usage.memory_bytes, self.requests.memory_bytes
        if used is None or reserved is None:
            return None
        return max(0, reserved - used)


class WorkloadRef(BaseModel):
    kind: str
    name: str

"""Classifies how far this tool may go when acting on a workload.

This is the safety boundary. It is computed once per snapshot, stamped onto
every workload and pod, and re-checked server-side before any mutation - the UI
disabling a button is a convenience, not the control.

Two facts from the live cluster shape this module:

1. Deployments and StatefulSets created by Helm carry no ownerReferences, so
   ownership cannot be read off the workload. It has to come from the *pods*,
   whose owner chain does reach the operator's custom resources.
2. The ArangoDB cluster members (agents, dbservers, coordinators, gateways) are
   owned by an ArangoDeployment. Scaling them through the core API is not just
   ineffective - the operator reconciles it straight back - it risks the
   database. They are resized through the ArangoDeployment spec instead.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models.common import Protection, ProtectionLevel

# Labels the operator stamps onto ArangoDB cluster members.
_ARANGO_MEMBER_LABELS = ("arango_deployment", "deployment.arangodb.com/member")

_OPERATOR_CHART_PREFIX = "kube-arangodb"


def _owner_kinds(pod: dict[str, Any]) -> set[str]:
    return {
        ref.get("kind", "")
        for ref in (pod.get("metadata", {}).get("ownerReferences") or [])
        if ref.get("kind")
    }


def classify_pod(pod: dict[str, Any], settings: Settings) -> Protection:
    """Classify a single pod. First match wins."""
    metadata = pod.get("metadata", {})
    labels = metadata.get("labels") or {}
    protected_kinds = set(settings.protected_owner_kind_list)

    owned_by = _owner_kinds(pod) & protected_kinds
    if owned_by:
        kind = sorted(owned_by)[0]
        owner_name = next(
            (
                ref.get("name", "")
                for ref in (metadata.get("ownerReferences") or [])
                if ref.get("kind") == kind
            ),
            "",
        )
        return Protection(
            level=ProtectionLevel.PROTECTED,
            reason=f"Managed by the ArangoDB operator ({kind}/{owner_name}).",
            remediation=(
                "Resize this from the Database page, which edits the "
                f"{kind} spec. The operator reconciles any direct change back."
            ),
        )

    # Belt and braces: the same members, identified by label rather than owner,
    # in case a pod is seen before its ownerReferences are populated.
    if any(label in labels for label in _ARANGO_MEMBER_LABELS):
        return Protection(
            level=ProtectionLevel.PROTECTED,
            reason="An ArangoDB cluster member, managed by the operator.",
            remediation="Resize this from the Database page, which edits the ArangoDeployment.",
        )

    chart = labels.get("helm.sh/chart", "")
    if chart.startswith(_OPERATOR_CHART_PREFIX):
        return Protection(
            level=ProtectionLevel.GUARDED,
            reason="This is the ArangoDB operator itself.",
            remediation=(
                "Stopping it freezes reconciliation for every Arango resource in "
                "this namespace. Set ARM_ALLOW_GUARDED_ACTIONS to override."
            ),
        )

    return Protection(level=ProtectionLevel.NORMAL)


def classify_workload(name: str, pods: list[dict[str, Any]], settings: Settings) -> Protection:
    """Classify a workload from its name and its pods.

    The strictest level found among the pods wins, so a workload is never more
    actionable than the things it owns.
    """
    for pod in pods:
        protection = classify_pod(pod, settings)
        if protection.level is ProtectionLevel.PROTECTED:
            return protection

    guarded = next(
        (
            classify_pod(pod, settings)
            for pod in pods
            if classify_pod(pod, settings).level is ProtectionLevel.GUARDED
        ),
        None,
    )
    if guarded is not None:
        return guarded

    if name in settings.guarded_name_list:
        return Protection(
            level=ProtectionLevel.GUARDED,
            reason="Platform infrastructure.",
            remediation=(
                "Other services depend on this. Set ARM_ALLOW_GUARDED_ACTIONS to override."
            ),
        )

    return Protection(level=ProtectionLevel.NORMAL)


def strictest(levels: list[Protection]) -> Protection:
    """The most restrictive protection among a set, used when rolling up."""
    order = {
        ProtectionLevel.PROTECTED: 0,
        ProtectionLevel.GUARDED: 1,
        ProtectionLevel.NORMAL: 2,
    }
    if not levels:
        return Protection(level=ProtectionLevel.NORMAL)
    return min(levels, key=lambda p: order[p.level])

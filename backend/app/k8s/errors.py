"""Translation of Kubernetes API exceptions into application-level errors."""

from __future__ import annotations

from kubernetes.client.exceptions import ApiException


class K8sError(Exception):
    """Base class for Kubernetes access problems surfaced to the API layer."""


class K8sConfigError(K8sError):
    """Raised at startup when no usable cluster configuration can be found."""


class K8sAccessDenied(K8sError):
    """The credential is not permitted to perform the requested operation."""


class K8sNotFound(K8sError):
    """The requested object does not exist."""


class K8sConflict(K8sError):
    """The object changed underneath us, or the API server rejected the change."""


def translate(exc: ApiException, what: str) -> K8sError:
    """Map an ApiException onto the narrower error types the API layer handles."""
    if exc.status == 403:
        return K8sAccessDenied(f"Not permitted to {what}.")
    if exc.status == 404:
        return K8sNotFound(f"{what}: not found.")
    if exc.status == 409:
        return K8sConflict(f"{what}: conflict — the object changed. Retry.")
    return K8sError(f"{what}: Kubernetes API returned {exc.status} {exc.reason}.")

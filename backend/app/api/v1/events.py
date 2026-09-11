"""Events and pod logs — the two things that explain a failure."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from kubernetes.client.exceptions import ApiException

from app.api.deps import ClientsDep
from app.models.inventory import EventSummary
from app.services import inventory as inventory_service

router = APIRouter(tags=["events"])

_LOG_TIMEOUT = 30


@router.get("/events", response_model=list[EventSummary])
def list_events(
    clients: ClientsDep,
    involved: str | None = None,
    service: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[EventSummary]:
    """Warning events, newest first, deduplicated with their counts summed."""
    snapshot = inventory_service.get_snapshot(clients)

    if service:
        events = list(snapshot.service_warnings.get(service, []))
    else:
        events = [event for group in snapshot.service_warnings.values() for event in group]

    if involved:
        events = [event for event in events if event.involved_name == involved]

    events.sort(key=lambda event: event.last_seen or "", reverse=True)
    return events[:limit]


@router.get("/pods/{name}/logs", response_class=PlainTextResponse)
def pod_logs(
    name: str,
    clients: ClientsDep,
    container: str | None = None,
    tail_lines: int = Query(200, ge=1, le=5000),
    previous: bool = False,
) -> PlainTextResponse:
    """Tail one container's log.

    `previous=true` reads the log of the *last terminated* instance, which is
    the only place the reason for a CrashLoopBackOff is written down.
    """
    try:
        # _preload_content=False returns the raw HTTP response. With the
        # default, the client runs the log body through its JSON deserialiser,
        # which hands back str(bytes) - the whole log rendered as a Python
        # repr on a single line, escapes and all.
        response = clients.core.read_namespaced_pod_log(
            name=name,
            namespace=clients.namespace,
            container=container,
            tail_lines=tail_lines,
            previous=previous,
            timestamps=False,
            _preload_content=False,
            _request_timeout=_LOG_TIMEOUT,
        )
        text = response.data
    except ApiException as exc:
        if exc.status == 404:
            raise HTTPException(404, f"No pod named {name!r}.") from exc
        if exc.status == 400:
            # Raised when the container never restarted and `previous` was
            # asked for, or when a multi-container pod needs `container`.
            raise HTTPException(400, _bad_request_detail(exc)) from exc
        raise

    return PlainTextResponse(_decode(text) or "(this container has produced no output)")


def _decode(text: object) -> str:
    """The client hands back bytes for some log responses and str for others.

    Left alone, the bytes case renders as a Python repr - b'...\\n...' on one
    line - which is unreadable. Decoding leniently keeps a log with odd bytes
    in it readable rather than failing the whole request.
    """
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text or "")


def _bad_request_detail(exc: ApiException) -> str:
    body = str(exc.body or "")
    if "previous terminated container" in body:
        return "This container has not terminated before, so there is no previous log."
    if "choose one of" in body or "container name must be specified" in body:
        return "This pod has several containers. Pick one."
    return "The API server rejected the log request."

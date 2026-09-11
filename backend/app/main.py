"""Arango Resource Manager API."""

from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.routes import api_router
from app.config import get_settings
from app.k8s.errors import K8sAccessDenied, K8sConflict, K8sError, K8sNotFound


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


_configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Arango Resource Manager",
    version=__version__,
    description=(
        "See and safely manage what is running in an ArangoDB Platform Kubernetes namespace."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(K8sError)
def handle_k8s_error(_request: Request, exc: K8sError) -> JSONResponse:
    """Map cluster access failures onto honest HTTP statuses."""
    status = 502
    if isinstance(exc, K8sAccessDenied):
        status = 403
    elif isinstance(exc, K8sNotFound):
        status = 404
    elif isinstance(exc, K8sConflict):
        status = 409
    log.warning("k8s.error", error=str(exc), status=status)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness only. It deliberately does not touch the cluster."""
    return {"status": "ok", "version": __version__}

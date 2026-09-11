"""Read routes over the GenAI projects in the namespace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import ClientsDep
from app.models.genai import GenAiProject, ProjectStatus
from app.services import inventory as inventory_service

router = APIRouter(prefix="/genai", tags=["genai"])


@router.get("/projects", response_model=list[GenAiProject])
def list_projects(
    clients: ClientsDep,
    status: ProjectStatus | None = None,
) -> list[GenAiProject]:
    """Every AutoGraph project with the retrievers running for it.

    Projects with no retriever, and retrievers whose project service is gone,
    are in this list too - carrying the status that says which they are.
    """
    projects = inventory_service.get_snapshot(clients).genai_projects
    if status is not None:
        projects = [p for p in projects if p.status is status]
    return projects


@router.get("/projects/{key:path}", response_model=GenAiProject)
def get_project(key: str, clients: ClientsDep) -> GenAiProject:
    """One project by its `<db>/<project>` key, which contains a slash."""
    projects = inventory_service.get_snapshot(clients).genai_projects
    project = next((p for p in projects if p.key == key), None)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No GenAI project keyed {key!r}.")
    return project

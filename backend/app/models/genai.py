"""GenAI models: an AutoGraph project and the retrievers running for it."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Protection, ResourceTriple


class GenAiRole(StrEnum):
    """What part a release plays in a GenAI project."""

    PROJECT = "project"
    """An `arangodb-autograph` release: the project service itself."""

    RETRIEVER = "retriever"
    IMPORTER = "importer"


class ProjectStatus(StrEnum):
    PAIRED = "paired"
    """A project service and at least one retriever, on the same project and db."""

    PROJECT_ONLY = "project_only"
    """A project with no retriever running: nothing can be queried."""

    RETRIEVER_ONLY = "retriever_only"
    """A retriever whose project service is gone - reclaimable, usually."""

    UNIDENTIFIED = "unidentified"
    """A GenAI release whose project could not be read, so it is not paired."""


class GenAiComponent(BaseModel):
    role: GenAiRole
    kind: str
    name: str
    """The Helm release name, e.g. "arangodb-graphrag-retriever-tl1bq"."""

    service: str | None = None
    """The service group this rolls up into, for linking to its detail page."""

    route_path: str | None = None
    chart_version: str | None = None

    desired_replicas: int = 0
    ready_replicas: int = 0
    pod_count: int = 0
    ready_pods: int = 0

    age_seconds: int | None = None
    """The oldest pod's age: how long this release has actually been serving."""

    restart_count: int = 0

    chat_model: str | None = None
    embedding_model: str | None = None

    protection: Protection = Field(default_factory=Protection)
    resources: ResourceTriple = Field(default_factory=ResourceTriple)
    warning_count: int = 0


class GenAiProject(BaseModel):
    key: str
    """Stable identifier: "<db>/<project>", or "unidentified"."""

    project_name: str | None = None
    db_name: str | None = None
    status: ProjectStatus

    project: GenAiComponent | None = None
    retrievers: list[GenAiComponent] = Field(default_factory=list)
    others: list[GenAiComponent] = Field(default_factory=list)
    """Importers and any future role, kept so nothing running is hidden."""

    resources: ResourceTriple = Field(default_factory=ResourceTriple)
    warning_count: int = 0

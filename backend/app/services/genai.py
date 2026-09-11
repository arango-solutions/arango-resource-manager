"""Pairs an AutoGraph project with the retriever running for it.

The release names cannot do this. `arangodb-autograph-ybsha` and
`arangodb-graphrag-retriever-tl1bq` are the same project; the suffixes are
random per install and share nothing. Nor can the Kubernetes metadata: no
ArangoPlatformService declares these releases, their labels carry only the
chart, and their ArangoRoute paths just echo the suffix back.

The association exists in one place - the pod spec. Both charts set
`GENAI_PROJECT_NAME` and `db_name` as literal environment values on their
`grpc-server` container, and the pair of them is the project's identity. Two
projects in the recorded namespace share one database, so the key is the
composite: matching on the project name alone would merge them.

Only the names in `ENV_KEYS` are read, and only when the entry carries a
literal `value`. An entry with a `valueFrom` is skipped rather than resolved,
so no secret or field reference is ever followed - a release whose project name
arrives that way is reported as unidentified instead of guessed at.
"""

from __future__ import annotations

from typing import Any

from app.models.common import ResourceTriple
from app.models.genai import GenAiComponent, GenAiProject, GenAiRole, ProjectStatus
from app.models.inventory import EventSummary, PodSummary, WorkloadSummary
from app.services.grouping import NAME_LABEL, labels_of, name_of

ROLE_BY_CHART = {
    "arangodb-autograph": GenAiRole.PROJECT,
    "arangodb-graphrag-retriever": GenAiRole.RETRIEVER,
    "arangodb-graphrag-importer": GenAiRole.IMPORTER,
}

# The container both charts run their service in, and the only one carrying the
# project identity. The others hold a proxy and an OpenTelemetry collector.
PRIMARY_CONTAINER = "grpc-server"

PROJECT_ENV = "GENAI_PROJECT_NAME"
DB_ENV = "db_name"

ENV_KEYS = frozenset(
    {
        PROJECT_ENV,
        DB_ENV,
        "SERVICE_ID",
        "AUTOGRAPH_SERVICE_ID",
        "chat_model",
        "embedding_model",
        "chat_api_provider",
        "embedding_api_provider",
        "embedding_dim",
    }
)

UNIDENTIFIED_KEY = "unidentified"


def role_of(workload: dict[str, Any]) -> GenAiRole | None:
    """The GenAI role of a raw Deployment or StatefulSet, if it has one."""
    return ROLE_BY_CHART.get(labels_of(workload).get(NAME_LABEL, ""))


def genai_env(workload: dict[str, Any]) -> dict[str, str]:
    """The allowlisted literal environment values on a raw workload.

    The primary container is read first so its values win. Nothing outside
    `ENV_KEYS` is read, and an entry with a `valueFrom` is skipped entirely.
    """
    template = (workload.get("spec") or {}).get("template") or {}
    containers = (template.get("spec") or {}).get("containers") or []
    ordered = sorted(containers, key=lambda c: c.get("name") != PRIMARY_CONTAINER)

    found: dict[str, str] = {}
    for container in ordered:
        for entry in container.get("env") or []:
            name = str(entry.get("name", ""))
            value = entry.get("value")
            if name not in ENV_KEYS or entry.get("valueFrom") is not None or value is None:
                continue
            found.setdefault(name, str(value))
    return found


def project_key(project_name: str | None, db_name: str | None) -> str:
    if not project_name:
        return UNIDENTIFIED_KEY
    return f"{db_name or ''}/{project_name}"


def build_projects(
    kinded: list[tuple[str, dict[str, Any]]],
    workloads: list[WorkloadSummary],
    pods: list[PodSummary],
    routes: dict[str, str],
    warnings: dict[str, list[EventSummary]],
) -> list[GenAiProject]:
    """Group every GenAI release by the project it serves.

    A project with no retriever and a retriever with no project are both real
    states - the first cannot answer a query, the second is usually a leftover
    holding reservations - so both are kept and labelled rather than dropped.
    """
    by_ref = {(w.kind, w.name): w for w in workloads}
    pods_by_workload: dict[tuple[str, str], list[PodSummary]] = {}
    for pod in pods:
        if pod.workload is not None:
            pods_by_workload.setdefault((pod.workload.kind, pod.workload.name), []).append(pod)

    grouped: dict[str, list[GenAiComponent]] = {}
    identity: dict[str, tuple[str | None, str | None]] = {}

    for kind, obj in kinded:
        role = role_of(obj)
        workload = by_ref.get((kind, name_of(obj)))
        if role is None or workload is None:
            continue

        env = genai_env(obj)
        project_name = env.get(PROJECT_ENV) or None
        db_name = env.get(DB_ENV) or None
        key = project_key(project_name, db_name)

        members = pods_by_workload.get((kind, workload.name), [])
        component = _component(role, workload, members, env, routes, warnings)

        grouped.setdefault(key, []).append(component)
        identity.setdefault(key, (project_name, db_name))

    projects = []
    for key, components in grouped.items():
        project_name, db_name = identity[key]
        project = next((c for c in components if c.role is GenAiRole.PROJECT), None)
        retrievers = sorted(
            (c for c in components if c.role is GenAiRole.RETRIEVER), key=lambda c: c.name
        )
        # Everything the two fields above do not carry: importers, and a second
        # project service on the same project. Counted in the totals either way,
        # so it has to be shown too rather than silently added.
        others = sorted(
            (c for c in components if c is not project and c.role is not GenAiRole.RETRIEVER),
            key=lambda c: c.name,
        )

        resources = ResourceTriple()
        for component in components:
            resources = resources + component.resources

        projects.append(
            GenAiProject(
                key=key,
                project_name=project_name,
                db_name=db_name,
                status=_status(key, project, retrievers),
                project=project,
                retrievers=retrievers,
                others=others,
                resources=resources,
                warning_count=sum(c.warning_count for c in components),
            )
        )

    return sorted(projects, key=lambda p: ((p.project_name or "").lower(), p.db_name or ""))


def _component(
    role: GenAiRole,
    workload: WorkloadSummary,
    pods: list[PodSummary],
    env: dict[str, str],
    routes: dict[str, str],
    warnings: dict[str, list[EventSummary]],
) -> GenAiComponent:
    related = {workload.name, *(pod.name for pod in pods)}
    return GenAiComponent(
        role=role,
        kind=workload.kind,
        name=workload.name,
        service=workload.service,
        route_path=routes.get(workload.name),
        chart_version=workload.chart_version,
        desired_replicas=workload.desired_replicas,
        ready_replicas=workload.ready_replicas,
        pod_count=workload.pod_count,
        ready_pods=sum(1 for pod in pods if pod.ready),
        # The oldest pod, not the youngest: a release that rolled one replica an
        # hour ago has still been serving for as long as its longest-lived one.
        age_seconds=max((p.age_seconds for p in pods if p.age_seconds is not None), default=None),
        restart_count=sum(pod.restart_count for pod in pods),
        chat_model=env.get("chat_model"),
        embedding_model=env.get("embedding_model"),
        protection=workload.protection,
        resources=workload.resources,
        warning_count=sum(event.count for name in related for event in warnings.get(name, [])),
    )


def _status(
    key: str,
    project: GenAiComponent | None,
    retrievers: list[GenAiComponent],
) -> ProjectStatus:
    if key == UNIDENTIFIED_KEY:
        return ProjectStatus.UNIDENTIFIED
    if project is not None and retrievers:
        return ProjectStatus.PAIRED
    if project is not None:
        return ProjectStatus.PROJECT_ONLY
    return ProjectStatus.RETRIEVER_ONLY

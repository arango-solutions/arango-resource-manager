"""Pairing an AutoGraph project with its retriever.

Built from inline objects rather than the recorded fixtures: the probe keeps
only the allowlisted environment names, and the fixtures committed before that
allowlist existed carry no environment at all - so a fixture-based test here
would assert against data that cannot express the thing being tested.

The shapes below are trimmed copies of what the live namespace returns.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models.genai import GenAiRole, ProjectStatus
from app.services.genai import genai_env
from app.services.inventory import assemble
from scripts.probe_cluster import _scrub

AUTOGRAPH = "arangodb-autograph"
RETRIEVER = "arangodb-graphrag-retriever"


def env(**values: str) -> list[dict[str, Any]]:
    return [{"name": name, "value": value} for name, value in values.items()]


def deployment(
    name: str,
    chart: str,
    container_env: list[dict[str, Any]] | None = None,
    replicas: int = 1,
) -> dict[str, Any]:
    labels = {
        "app.kubernetes.io/instance": name,
        "app.kubernetes.io/name": chart,
        "helm.sh/chart": f"{chart}-v0.0.20",
    }
    return {
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {
                            "name": "grpc-server",
                            "image": f"registry.example.com/{chart}:v0.0.20",
                            "env": container_env or [],
                            "resources": {
                                "requests": {"cpu": "250m", "memory": "256Mi"},
                                "limits": {"cpu": "2", "memory": "2Gi"},
                            },
                        },
                        {
                            "name": "proxy-server",
                            "image": f"registry.example.com/{chart}:v0.0.20",
                            "env": env(HTTP_PORT="8080"),
                            "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}},
                        },
                    ]
                },
            },
        },
        "status": {"replicas": replicas, "readyReplicas": replicas},
    }


def replicaset(name: str, owner: str) -> dict[str, Any]:
    return {
        "metadata": {
            "name": name,
            "ownerReferences": [{"kind": "Deployment", "name": owner}],
        }
    }


def pod(name: str, replicaset_name: str, restarts: int = 0) -> dict[str, Any]:
    return {
        "metadata": {
            "name": name,
            "creationTimestamp": "2026-09-01T00:00:00Z",
            "ownerReferences": [{"kind": "ReplicaSet", "name": replicaset_name}],
        },
        "spec": {
            "containers": [
                {
                    "name": name,
                    "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}},
                }
                for name in ("grpc-server", "proxy-server")
            ]
        },
        "status": {
            "phase": "Running",
            "startTime": "2026-09-01T00:00:00Z",
            "containerStatuses": [
                {"name": "grpc-server", "ready": True, "restartCount": restarts},
                {"name": "proxy-server", "ready": True, "restartCount": 0},
            ],
        },
    }


def snapshot_of(
    deployments: list[dict[str, Any]],
    routes: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> Any:
    """Assemble a snapshot with one running pod behind every deployment."""
    replicasets = []
    pods = []
    for workload in deployments:
        name = workload["metadata"]["name"]
        replicasets.append(replicaset(f"{name}-abc123", name))
        pods.append(pod(f"{name}-abc123-xyz", f"{name}-abc123"))

    raw = {
        "pods": pods,
        "deployments": deployments,
        "replicasets": replicasets,
        "routes": routes or [],
        "events": events or [],
    }
    return assemble(raw, "example-platform", Settings())


def test_project_and_retriever_pair_on_the_composite_key() -> None:
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-ybsha",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-retriever-tl1bq",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
        ]
    ).genai_projects

    assert len(projects) == 1
    project = projects[0]
    assert project.status is ProjectStatus.PAIRED
    assert project.project_name == "sec_filings_v2"
    assert project.db_name == "sec_filings"
    assert project.key == "sec_filings/sec_filings_v2"
    assert project.project is not None
    assert project.project.name == "arangodb-autograph-ybsha"
    assert project.project.role is GenAiRole.PROJECT
    assert [r.name for r in project.retrievers] == ["arangodb-graphrag-retriever-tl1bq"]


def test_two_projects_sharing_a_database_do_not_merge() -> None:
    """The reason the key is composite rather than the project name alone."""
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-6i7pz",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec-test", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-autograph-ybsha",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-retriever-tl1bq",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
        ]
    ).genai_projects

    by_name = {p.project_name: p for p in projects}
    assert set(by_name) == {"sec-test", "sec_filings_v2"}
    assert by_name["sec-test"].status is ProjectStatus.PROJECT_ONLY
    assert by_name["sec-test"].retrievers == []
    assert by_name["sec_filings_v2"].status is ProjectStatus.PAIRED


def test_a_project_with_no_retriever_is_kept_and_labelled() -> None:
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-6i7pz",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec-test", db_name="sec_filings"),
            )
        ]
    ).genai_projects

    assert len(projects) == 1
    assert projects[0].status is ProjectStatus.PROJECT_ONLY
    assert projects[0].project is not None


def test_a_retriever_with_no_project_is_kept_and_labelled() -> None:
    """The leftover case: the project service is gone, the retriever still runs."""
    projects = snapshot_of(
        [
            deployment(
                "arangodb-graphrag-retriever-gvxrm",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="Coral", db_name="health_universe"),
            )
        ]
    ).genai_projects

    assert len(projects) == 1
    project = projects[0]
    assert project.status is ProjectStatus.RETRIEVER_ONLY
    assert project.project is None
    assert project.project_name == "Coral"
    assert [r.name for r in project.retrievers] == ["arangodb-graphrag-retriever-gvxrm"]


def test_two_retrievers_on_one_project_both_appear() -> None:
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-ybsha",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-retriever-tl1bq",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-retriever-aaaaa",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
        ]
    ).genai_projects

    assert len(projects) == 1
    assert [r.name for r in projects[0].retrievers] == [
        "arangodb-graphrag-retriever-aaaaa",
        "arangodb-graphrag-retriever-tl1bq",
    ]
    # Three releases at half a core each, all charged to this one project.
    assert projects[0].resources.requests.cpu_cores == 1.5


def test_a_second_project_service_is_shown_not_just_counted() -> None:
    """Two AutoGraph releases on one project: whatever the totals charge for
    has to appear somewhere, or the card adds up to more than it lists."""
    project_env = env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings")
    projects = snapshot_of(
        [
            deployment("arangodb-autograph-ybsha", AUTOGRAPH, project_env),
            deployment("arangodb-autograph-zzzzz", AUTOGRAPH, project_env),
            deployment("arangodb-graphrag-retriever-tl1bq", RETRIEVER, project_env),
        ]
    ).genai_projects

    assert len(projects) == 1
    project = projects[0]
    assert project.project is not None
    listed = [project.project.name, *(c.name for c in project.others)]
    assert sorted(listed) == ["arangodb-autograph-ybsha", "arangodb-autograph-zzzzz"]
    assert project.resources.requests.cpu_cores == 1.5


def test_an_importer_is_kept_beside_the_project_it_serves() -> None:
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-ybsha",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-importer-qqqqq",
                "arangodb-graphrag-importer",
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
        ]
    ).genai_projects

    assert len(projects) == 1
    assert [c.name for c in projects[0].others] == ["arangodb-graphrag-importer-qqqqq"]
    assert projects[0].others[0].role is GenAiRole.IMPORTER
    # An importer is not a retriever: this project still cannot answer a query.
    assert projects[0].status is ProjectStatus.PROJECT_ONLY


def test_a_project_name_behind_a_secret_ref_is_unidentified_not_guessed() -> None:
    """Nothing here resolves a valueFrom, so nothing here may pretend to know."""
    retriever = deployment("arangodb-graphrag-retriever-lsoej", RETRIEVER, [])
    retriever["spec"]["template"]["spec"]["containers"][0]["env"] = [
        {
            "name": "GENAI_PROJECT_NAME",
            "valueFrom": {"secretKeyRef": {"name": "project", "key": "name"}},
        },
        {"name": "db_name", "value": "ARGUS"},
    ]

    projects = snapshot_of([retriever]).genai_projects
    assert len(projects) == 1
    assert projects[0].status is ProjectStatus.UNIDENTIFIED
    assert projects[0].key == "unidentified"
    assert projects[0].project_name is None
    assert [r.name for r in projects[0].retrievers] == ["arangodb-graphrag-retriever-lsoej"]


def test_non_genai_workloads_are_ignored() -> None:
    snapshot = snapshot_of(
        [
            deployment("arangodb-file-parser-api", "arangodb-file-parser", env(WORKERS="4")),
            deployment(
                "arangodb-graphrag-retriever-tl1bq",
                RETRIEVER,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
        ]
    )

    assert len(snapshot.genai_projects) == 1
    assert snapshot.genai_projects[0].project_name == "sec_filings_v2"
    # The file parser is still in the snapshot; it is just not a GenAI project.
    assert any(w.name == "arangodb-file-parser-api" for w in snapshot.workloads)


def test_components_carry_what_the_page_shows() -> None:
    routes = [
        {
            "metadata": {"name": "arangodb-graphrag-retriever-tl1bq"},
            "spec": {"route": {"path": "/graphrag/retriever/tl1bq/"}},
        }
    ]
    events = [
        {
            "type": "Warning",
            "reason": "InstallFailed",
            "message": "db_name is required to install the service",
            "count": 7,
            "involvedObject": {"kind": "Deployment", "name": "arangodb-graphrag-retriever-tl1bq"},
        }
    ]
    projects = snapshot_of(
        [
            deployment(
                "arangodb-autograph-ybsha",
                AUTOGRAPH,
                env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings"),
            ),
            deployment(
                "arangodb-graphrag-retriever-tl1bq",
                RETRIEVER,
                env(
                    GENAI_PROJECT_NAME="sec_filings_v2",
                    db_name="sec_filings",
                    chat_model="gpt-5",
                    embedding_model="text-embedding-3-large",
                ),
            ),
        ],
        routes=routes,
        events=events,
    ).genai_projects

    retriever = projects[0].retrievers[0]
    assert retriever.route_path == "/graphrag/retriever/tl1bq/"
    assert retriever.chart_version == "v0.0.20"
    assert retriever.chat_model == "gpt-5"
    assert retriever.embedding_model == "text-embedding-3-large"
    assert retriever.pod_count == 1
    assert retriever.ready_pods == 1
    assert retriever.age_seconds and retriever.age_seconds > 0
    assert retriever.service == "arangodb-graphrag-retriever-tl1bq"
    assert retriever.warning_count == 7
    assert projects[0].warning_count == 7
    # The project service and its retriever together: one core reserved.
    assert projects[0].resources.requests.cpu_cores == 1.0


def test_only_allowlisted_environment_names_are_read() -> None:
    """The allowlist is what is read, not what is redacted afterwards."""
    workload = deployment(
        "arangodb-graphrag-retriever-tl1bq",
        RETRIEVER,
        env(
            GENAI_PROJECT_NAME="sec_filings_v2",
            db_name="sec_filings",
            OPENAI_API_KEY="sk-do-not-read-this",
            FILE_PARSER_RECOVERY_USERNAME="root",
        ),
    )

    read = genai_env(workload)
    assert read == {"GENAI_PROJECT_NAME": "sec_filings_v2", "db_name": "sec_filings"}


def test_the_primary_container_wins_when_two_disagree() -> None:
    workload = deployment(
        "arangodb-graphrag-retriever-tl1bq",
        RETRIEVER,
        env(GENAI_PROJECT_NAME="from-grpc-server"),
    )
    containers = workload["spec"]["template"]["spec"]["containers"]
    containers[1]["env"] = env(GENAI_PROJECT_NAME="from-proxy")
    # Order the primary container second, so position cannot be what decides.
    containers.reverse()

    assert genai_env(workload)["GENAI_PROJECT_NAME"] == "from-grpc-server"


def test_the_probe_records_only_allowlisted_literal_env() -> None:
    """A recorded fixture must carry the pairing key and nothing else."""
    workload = deployment(
        "arangodb-graphrag-retriever-tl1bq",
        RETRIEVER,
        env(GENAI_PROJECT_NAME="sec_filings_v2", db_name="sec_filings", OPENAI_API_KEY="sk-secret"),
    )
    workload["spec"]["template"]["spec"]["containers"][0]["env"].append(
        {
            "name": "chat_model",
            "valueFrom": {"secretKeyRef": {"name": "models", "key": "chat"}},
        }
    )

    scrubbed = _scrub(workload)
    containers = scrubbed["spec"]["template"]["spec"]["containers"]
    assert containers[0]["env"] == [
        {"name": "GENAI_PROJECT_NAME", "value": "sec_filings_v2"},
        {"name": "db_name", "value": "sec_filings"},
    ]
    # The proxy container's only variable is not allowlisted, so env goes entirely.
    assert "env" not in containers[1]

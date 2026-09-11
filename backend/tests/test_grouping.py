"""Grouping, asserted against the recorded fixtures.

These are the guard rails for the whole app: if grouping is wrong, every
number and every action button is attached to the wrong thing.
"""

from __future__ import annotations

from typing import Any

from app.services.grouping import (
    ROLE_TO_TIER,
    build_pod_index,
    chart_version,
    conditions_of,
    name_of,
    resolve_services,
    route_index,
)
from tests.conftest import fixture_items

PROTECTED_KINDS = {"ArangoDeployment", "ArangoMLExtension", "ArangoMLBatchJob"}


def test_exact_match_wins_before_prefix_match(
    deployments: list[dict[str, Any]], platform_services: list[dict[str, Any]]
) -> None:
    """The collision that a naive prefix match gets wrong.

    `arangodb-platform-ui` and `arangodb-platform-ui-server` are both services.
    Matching by prefix alone lets the former swallow the latter's deployment.
    """
    service_names = {name_of(s) for s in platform_services}
    assert {"arangodb-platform-ui", "arangodb-platform-ui-server"} <= service_names

    resolved = resolve_services(deployments, platform_services)
    assert resolved["arangodb-platform-ui-server"] == ("arangodb-platform-ui-server", "exact")
    assert resolved["arangodb-platform-ui"] == ("arangodb-platform-ui", "exact")


def test_satellite_releases_land_under_their_service(
    deployments: list[dict[str, Any]], platform_services: list[dict[str, Any]]
) -> None:
    """The three graphrag retriever releases belong to one service."""
    resolved = resolve_services(deployments, platform_services)
    satellites = [n for n in resolved if n.startswith("arangodb-graphrag-retriever-")]
    assert len(satellites) == 3
    for workload in satellites:
        service, confidence = resolved[workload]
        assert service == "arangodb-graphrag-retriever"
        assert confidence == "instance"


def test_file_parser_components_group_together(
    deployments: list[dict[str, Any]], platform_services: list[dict[str, Any]]
) -> None:
    """Four deployments - api, orchestrator, and two worker pools - one service."""
    resolved = resolve_services(deployments, platform_services)
    members = sorted(n for n, (svc, _) in resolved.items() if svc == "arangodb-file-parser")
    assert members == [
        "arangodb-file-parser-api",
        "arangodb-file-parser-orchestrator",
        "arangodb-file-parser-worker-default",
        "arangodb-file-parser-worker-pdf",
    ]


def test_workloads_without_a_service_are_kept_as_unmanaged(
    deployments: list[dict[str, Any]], platform_services: list[dict[str, Any]]
) -> None:
    """The operator and autograph match no ArangoPlatformService. They still appear."""
    resolved = resolve_services(deployments, platform_services)
    assert resolved["arango-operator-operator"][1] == "unmanaged"
    autograph = [n for n in resolved if n.startswith("arangodb-autograph")]
    assert autograph, "expected an autograph deployment"
    assert all(resolved[n][1] == "unmanaged" for n in autograph)


def test_every_workload_resolves_to_something(
    deployments: list[dict[str, Any]],
    statefulsets: list[dict[str, Any]],
    platform_services: list[dict[str, Any]],
) -> None:
    workloads = deployments + statefulsets
    resolved = resolve_services(workloads, platform_services)
    assert len(resolved) == len(workloads)
    assert all(svc for svc, _ in resolved.values())


def test_a_service_may_own_no_workloads_at_all(
    deployments: list[dict[str, Any]], platform_services: list[dict[str, Any]]
) -> None:
    """The retriever service exists but its install is failing, so nothing runs
    under its own name. A group with zero workloads is a real state."""
    resolved = resolve_services(deployments, platform_services)
    exact = {svc for svc, conf in resolved.values() if conf == "exact"}
    unclaimed = {name_of(s) for s in platform_services} - exact
    assert "arangodb-graphrag-retriever" in unclaimed


def test_pods_resolve_to_their_deployment_not_their_replicaset(
    pods: list[dict[str, Any]],
) -> None:
    replicasets = fixture_items("replicasets")
    index, standalone = build_pod_index(pods, replicasets, PROTECTED_KINDS)

    assert not standalone, "no bare pods expected in this namespace"
    assert ("Deployment", "arangodb-file-parser-worker-pdf") in index
    assert len(index[("Deployment", "arangodb-file-parser-worker-pdf")]) == 25
    assert len(index[("Deployment", "arangodb-file-parser-worker-default")]) == 5
    # Nothing should be left pointing at a ReplicaSet.
    assert not [key for key in index if key[0] == "ReplicaSet"]


def test_operator_owned_pods_group_by_role(pods: list[dict[str, Any]]) -> None:
    """The ArangoDB cluster members are keyed by role, never by parsing the
    abbreviations in their pod names (agnt / prmr / crdn / gway)."""
    replicasets = fixture_items("replicasets")
    index, _ = build_pod_index(pods, replicasets, PROTECTED_KINDS)

    roles = {key[1] for key in index if key[0] == "ArangoDeployment"}
    assert roles, "expected operator-owned pods"
    assert roles <= set(ROLE_TO_TIER), f"unmapped roles: {roles - set(ROLE_TO_TIER)}"

    member_count = sum(len(v) for k, v in index.items() if k[0] == "ArangoDeployment")
    assert member_count == 12


def test_every_pod_is_accounted_for(pods: list[dict[str, Any]]) -> None:
    replicasets = fixture_items("replicasets")
    index, standalone = build_pod_index(pods, replicasets, PROTECTED_KINDS)
    grouped = sum(len(v) for v in index.values()) + len(standalone)
    assert grouped == len(pods)


def test_chart_version_survives_dashes_in_the_chart_name(
    deployments: list[dict[str, Any]],
) -> None:
    by_name = {name_of(d): d for d in deployments}
    # helm.sh/chart is "arangodb-file-parser-v0.1.3"; splitting on "-" would
    # return "parser".
    assert chart_version(by_name["arangodb-file-parser-api"]) == "v0.1.3"


def test_conditions_carry_their_message(platform_services: list[dict[str, Any]]) -> None:
    """A failing service must explain itself, not just report False."""
    retriever = next(s for s in platform_services if name_of(s) == "arangodb-graphrag-retriever")
    conditions = conditions_of(retriever)
    assert conditions, "expected status conditions"
    failing = [c for c in conditions if not c["status"]]
    assert failing, "the retriever install is expected to be failing"
    assert any(c.get("message") for c in failing)


def test_routes_expose_public_paths() -> None:
    routes = route_index(fixture_items("arangoroutes"))
    assert routes, "expected ArangoRoutes"
    assert all(path.startswith("/") for path in routes.values())

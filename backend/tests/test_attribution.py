"""Attribution: resolving an opaque release suffix to the project it serves."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.models.common import Attribution
from app.models.inventory import InventorySnapshot
from app.services.attribution import attribution_of, merge_attribution
from app.services.inventory import assemble
from tests.conftest import fixture_items


@pytest.fixture
def snapshot() -> InventorySnapshot:
    raw = {
        "pods": fixture_items("pods"),
        "deployments": fixture_items("deployments"),
        "statefulsets": fixture_items("statefulsets"),
        "replicasets": fixture_items("replicasets"),
        "platform_services": fixture_items("arangoplatformservices"),
        "charts": fixture_items("arangoplatformcharts"),
        "routes": fixture_items("arangoroutes"),
        "arango_deployments": fixture_items("arangodeployments"),
        "events": fixture_items("events"),
    }
    return assemble(raw, "example-platform", Settings())


def pod(*containers: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {"name": "p"}, "spec": {"containers": list(containers)}}


def container(name: str, **env: str) -> dict[str, Any]:
    return {
        "name": name,
        "image": "example/image:1",
        "resources": {},
        "env": [{"name": k, "value": v} for k, v in env.items()],
    }


class TestAttributionOf:
    def test_reads_project_and_database_from_grpc_server(self) -> None:
        result = attribution_of(
            pod(container("grpc-server", GENAI_PROJECT_NAME="widgets", db_name="widget_docs"))
        )
        assert result == Attribution(
            project="widgets", database="widget_docs", source="grpc-server"
        )

    def test_database_without_project_is_still_attribution(self) -> None:
        """A real state: some installs set only `db_name`."""
        result = attribution_of(pod(container("grpc-server", db_name="widget_docs")))
        assert result is not None
        assert result.project is None
        assert result.database == "widget_docs"

    def test_pod_with_no_attribution_env_returns_none(self) -> None:
        assert attribution_of(pod(container("grpc-server", OTEL_ENDPOINT="http://x"))) is None

    def test_pod_with_no_containers_returns_none(self) -> None:
        assert attribution_of({"spec": {}}) is None

    def test_grpc_server_wins_over_other_containers(self) -> None:
        """Sidecars carry their own env; the ordered candidate list decides."""
        result = attribution_of(
            pod(
                container("integration", db_name="sidecar_db"),
                container("grpc-server", db_name="real_db"),
            )
        )
        assert result is not None
        assert result.database == "real_db"
        assert result.source == "grpc-server"

    def test_falls_back_to_an_unlisted_container(self) -> None:
        """A differently packaged service is still attributed, not skipped."""
        result = attribution_of(pod(container("custom-main", db_name="other_db")))
        assert result is not None
        assert result.database == "other_db"
        assert result.source == "custom-main"

    def test_value_from_references_are_ignored(self) -> None:
        """Resolving a secretKeyRef would mean reading secrets for a display label."""
        c = container("grpc-server")
        c["env"] = [{"name": "db_name", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}}]
        assert attribution_of(pod(c)) is None

    def test_blank_values_do_not_count_as_attribution(self) -> None:
        assert attribution_of(pod(container("grpc-server", db_name="   "))) is None


class TestMergeAttribution:
    def test_agreeing_pods_merge_to_one_value(self) -> None:
        one = Attribution(project="widgets", database="widget_docs", source="grpc-server")
        merged = merge_attribution([one, one.model_copy()])
        assert merged is not None
        assert merged.project == "widgets"
        assert merged.database == "widget_docs"
        assert merged.conflict is False

    def test_disagreement_is_reported_not_silently_resolved(self) -> None:
        merged = merge_attribution(
            [
                Attribution(project="widgets", database="widget_docs"),
                Attribution(project="gadgets", database="widget_docs"),
            ]
        )
        assert merged is not None
        assert merged.conflict is True
        assert merged.project is None, "a conflicting field is withheld, not guessed"
        assert merged.database == "widget_docs", "the agreeing field survives the conflict"

    def test_unattributed_pods_are_skipped(self) -> None:
        merged = merge_attribution([None, Attribution(database="widget_docs"), None])
        assert merged is not None
        assert merged.database == "widget_docs"
        assert merged.conflict is False

    def test_all_none_merges_to_none(self) -> None:
        assert merge_attribution([None, None]) is None

    def test_empty_merges_to_none(self) -> None:
        assert merge_attribution([]) is None


class TestAttributionInInventory:
    """The end-to-end path, against the recorded fixtures."""

    def test_service_carries_attribution_from_its_pods(self, snapshot: InventorySnapshot) -> None:
        services = {s.name: s for s in snapshot.services}
        autograph = next(s for k, s in services.items() if k.startswith("arangodb-autograph"))
        assert autograph.attribution is not None
        assert autograph.attribution.project == "widget-catalog"
        assert autograph.attribution.database == "widget_docs"
        assert autograph.attribution.conflict is False

    def test_satellite_releases_serving_different_databases_report_a_conflict(
        self, snapshot: InventorySnapshot
    ) -> None:
        """The retriever's satellite Helm releases are grouped under one service.

        They need not serve the same corpus, and here they do not. The database
        is withheld rather than resolved to whichever pod sorted first; the
        project, which they agree on, still comes through.
        """
        retriever = next(s for s in snapshot.services if s.name == "arangodb-graphrag-retriever")
        assert retriever.attribution is not None
        assert retriever.attribution.conflict is True
        assert retriever.attribution.database is None
        assert retriever.attribution.project == "widget-catalog"

    def test_unattributed_service_reports_none_rather_than_guessing(
        self, snapshot: InventorySnapshot
    ) -> None:
        unattributed = [
            s
            for s in snapshot.services
            if s.name.startswith("arangodb-file-parser") and s.attribution is not None
        ]
        assert unattributed == [], "file-parser carries no attribution env"

    def test_pods_carry_their_own_attribution(self, snapshot: InventorySnapshot) -> None:
        attributed = [p for p in snapshot.pods if p.attribution is not None]
        assert len(attributed) == 3
        assert all(p.attribution.source == "grpc-server" for p in attributed)

"""Application settings, loaded from the environment and an optional .env file."""

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _blank_to_none(value: object) -> object:
    """Treat an unset env var (VAR=) as absent rather than as a parse error."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalFloat = Annotated[float | None, BeforeValidator(_blank_to_none)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ARM_", extra="ignore", case_sensitive=False
    )

    # Cluster connection. Empty values fall back to kubeconfig / in-cluster defaults.
    kube_context: str = ""
    kubeconfig: str = ""
    namespace: str = ""

    # Safety gates. read_only is the master kill switch for every mutating route.
    read_only: bool = True
    allow_guarded_actions: bool = False
    allow_database_scaling: bool = False

    protected_owner_kinds: str = "ArangoDeployment,ArangoMLExtension,ArangoMLBatchJob"
    guarded_names: str = (
        "arango-operator-operator,arango-control-plane,arangodb-platform-ui,"
        "arangodb-platform-ui-server,arangodb-core-ui,platform-monitoring-grafana,"
        "platform-monitoring-prometheus-server"
    )

    # Capacity budget: auto (derive from requests), manual (explicit), quota (ResourceQuota).
    budget_mode: str = "auto"
    budget_cpu_cores: OptionalFloat = None
    budget_memory_gi: OptionalFloat = None
    budget_headroom_factor: float = 1.25

    inventory_ttl_seconds: float = 5.0
    metrics_ttl_seconds: float = 15.0

    prometheus_url: str = ""
    cost_per_core_hour: float = 0.0
    cost_per_gi_hour: float = 0.0

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def protected_owner_kind_list(self) -> list[str]:
        return _csv(self.protected_owner_kinds)

    @property
    def guarded_name_list(self) -> list[str]:
        return _csv(self.guarded_names)

    @property
    def cors_origin_list(self) -> list[str]:
        return _csv(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()

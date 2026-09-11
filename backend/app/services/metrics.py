"""Live CPU and memory usage from metrics-server.

There is no typed metrics class in the Python client, so this goes through
CustomObjectsApi against metrics.k8s.io.

Two properties matter downstream:

1. A pod missing from the response has usage None, never 0. metrics-server
   lags a freshly scheduled pod by a scrape interval, and a restarting pod
   reporting 0 would look perfectly efficient - the exact opposite of true.
2. This is one instantaneous sample, not an average. Everything derived from
   it is labelled "now" in the UI; trends need Prometheus, which is a later
   phase and deliberately not on this path.
"""

from __future__ import annotations

import structlog
from kubernetes.client.exceptions import ApiException

from app.config import get_settings
from app.k8s.client import METRICS_GROUP, METRICS_VERSION, KubeClients
from app.models.common import Resources
from app.services.cache import TTLCache
from app.services.quantities import add_optional, parse_cpu, parse_memory

log = structlog.get_logger(__name__)

_TIMEOUT = 20

UsageMap = dict[str, Resources]
"""Pod name -> summed usage across its containers."""


def fetch_usage(clients: KubeClients) -> UsageMap:
    """One read of metrics.k8s.io. Raises ApiException if it is unavailable."""
    response = clients.custom.list_namespaced_custom_object(
        group=METRICS_GROUP,
        version=METRICS_VERSION,
        namespace=clients.namespace,
        plural="pods",
        _request_timeout=_TIMEOUT,
    )

    usage: UsageMap = {}
    for item in response.get("items", []):
        name = str((item.get("metadata") or {}).get("name", ""))
        if not name:
            continue

        cpu: float | None = None
        memory: float | None = None
        for container in item.get("containers", []) or []:
            block = container.get("usage") or {}
            cpu = add_optional(cpu, parse_cpu(block.get("cpu")))
            memory = add_optional(memory, parse_memory(block.get("memory")))

        usage[name] = Resources(
            cpu_cores=cpu,
            memory_bytes=None if memory is None else int(memory),
        )

    return usage


class _UsageCache:
    """Caches usage, and keeps serving the last good sample through a blip.

    metrics-server restarts and brief unavailability are routine. Blanking
    every usage figure in the UI for that window would be a worse answer than
    showing a sample a few seconds old, so the previous value is retained and
    only a sustained outage degrades to unknown.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._cache: TTLCache[UsageMap] = TTLCache(settings.metrics_ttl_seconds)
        self._last_good: UsageMap = {}
        self.available = True

    def get(self, clients: KubeClients) -> UsageMap:
        def load() -> UsageMap:
            try:
                usage = fetch_usage(clients)
            except ApiException as exc:
                log.warning("metrics.unavailable", status=exc.status)
                self.available = False
                return self._last_good
            self.available = True
            self._last_good = usage
            return usage

        return self._cache.get(load)


_usage_cache = _UsageCache()


def get_usage(clients: KubeClients) -> UsageMap:
    return _usage_cache.get(clients)


def is_available() -> bool:
    return _usage_cache.available

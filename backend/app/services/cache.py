"""A small TTL cache. Not worth a dependency."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TTLCache[T]:
    """Caches one value for a fixed number of seconds, refreshed on demand.

    The lock makes a refresh single-flight: when several requests arrive at once
    on a cold cache, one fetches and the rest wait for it rather than all
    hammering the API server.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._value: T | None = None
        self._fetched_at = 0.0

    def get(self, loader: Callable[[], T]) -> T:
        now = time.monotonic()
        value = self._value
        if value is not None and now - self._fetched_at < self._ttl:
            return value

        with self._lock:
            now = time.monotonic()
            if self._value is not None and now - self._fetched_at < self._ttl:
                return self._value
            loaded = loader()
            self._value = loaded
            self._fetched_at = time.monotonic()
            return loaded

    def invalidate(self) -> None:
        """Drop the cached value so the next read refetches.

        Called after a mutation, so the user sees the effect of their action
        immediately rather than up to a TTL later.
        """
        with self._lock:
            self._value = None
            self._fetched_at = 0.0

"""Durable record of what this tool did, and what it needs to undo it.

Two things live here. The previous replica count of anything stopped, written
*before* the scale-to-zero so the way back exists even if the process dies
mid-action. And an append-only log of every action, so "what happened to this
service" has an answer.

A JSON file is enough: the volume is tiny and the data is operational, not
something to run queries over. Writes go to a temp file and are renamed into
place, so a crash mid-write leaves the previous good file rather than a
truncated one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_MAX_HISTORY = 500


class StateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    # -- reading ---------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"stopped": {}, "history": []}
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt state file must not take the app down. The cost is a
            # forgotten replica count, which the UI reports honestly.
            log.warning("state.unreadable", path=str(self._path), error=str(exc))
            return {"stopped": {}, "history": []}
        data.setdefault("stopped", {})
        data.setdefault("history", [])
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w") as file:
                json.dump(data, file, indent=2, sort_keys=True)
            os.replace(temp_path, self._path)
        except OSError:
            Path(temp_path).unlink(missing_ok=True)
            raise

    @staticmethod
    def key(namespace: str, kind: str, name: str) -> str:
        return f"{namespace}/{kind}/{name}"

    # -- stopped workloads ----------------------------------------------

    def record_stop(
        self, namespace: str, kind: str, name: str, previous_replicas: int, actor: str
    ) -> None:
        """Remember what to restore to. Called before the scale, never after."""
        with self._lock:
            data = self._read()
            data["stopped"][self.key(namespace, kind, name)] = {
                "previous_replicas": previous_replicas,
                "stopped_at": datetime.now(UTC).isoformat(),
                "actor": actor,
            }
            self._write(data)

    def get_stop(self, namespace: str, kind: str, name: str) -> dict[str, Any] | None:
        return self._read()["stopped"].get(self.key(namespace, kind, name))

    def clear_stop(self, namespace: str, kind: str, name: str) -> None:
        with self._lock:
            data = self._read()
            data["stopped"].pop(self.key(namespace, kind, name), None)
            self._write(data)

    def all_stopped(self) -> dict[str, dict[str, Any]]:
        return dict(self._read()["stopped"])

    # -- history ---------------------------------------------------------

    def append_history(self, entry: dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            entry = {"ts": datetime.now(UTC).isoformat(), **entry}
            data["history"].append(entry)
            data["history"] = data["history"][-_MAX_HISTORY:]
            self._write(data)

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self._read()["history"]))[:limit]


_store = StateStore(Path(__file__).resolve().parent.parent.parent / ".arm-state.json")


def get_store() -> StateStore:
    return _store

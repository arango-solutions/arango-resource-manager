"""Project attribution: resolving an opaque release name to what it is *for*.

A GenAI service's release name carries a random five-character suffix chosen by
the control plane — `arangodb-graphrag-retriever-tl1bq`. Nothing in the
Kubernetes metadata says who created it, which project it serves, or which
database it reads: every one of these workloads carries only Helm boilerplate
(`app.kubernetes.io/*`, `helm.sh/chart`, `release`, `type`). Labelling
discipline cannot fix that, because humans do not write these manifests — the
control plane generates them, suffix and all.

The attribution is recoverable from one place nothing else looks: the
`grpc-server` container's environment, which carries `db_name` and
`GENAI_PROJECT_NAME`. That resolves `tl1bq` to `sec_filiings_v2` on
`sec_filings`, which is the difference between a list of opaque ids and a list
of things a person can make a decision about.

This module reads only the pod spec, so it needs no credentials beyond the pod
read the inventory layer already has, and it never contacts ArangoDB.
"""

from __future__ import annotations

from typing import Any

from app.models.common import Attribution

# Checked in order; the first container that yields anything wins. `grpc-server`
# is where the GenAI services put it, but the list is ordered rather than fixed
# so a differently-packaged service can still be attributed.
CANDIDATE_CONTAINERS = ("grpc-server", "server", "python-service-grpc", "worker")

PROJECT_KEYS = ("GENAI_PROJECT_NAME", "PROJECT_NAME")
DATABASE_KEYS = ("db_name", "DB_NAME", "DATABASE_NAME")


def _env_of(container: dict[str, Any]) -> dict[str, str]:
    """Literal env values only.

    `valueFrom` entries (secret and configmap references) are deliberately
    skipped: resolving them would mean reading secrets, which this tool has no
    business doing for a display label.
    """
    out: dict[str, str] = {}
    for entry in container.get("env") or []:
        name, value = entry.get("name"), entry.get("value")
        if isinstance(name, str) and isinstance(value, str):
            out[name] = value
    return out


def _first(env: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = env.get(key)
        if value and value.strip():
            return value.strip()
    return None


def attribution_of(pod: dict[str, Any]) -> Attribution | None:
    """Project and database for one pod, or None when it carries neither."""
    containers = {str(c.get("name", "")): c for c in (pod.get("spec", {}).get("containers") or [])}

    ordered = [containers[n] for n in CANDIDATE_CONTAINERS if n in containers]
    ordered += [c for n, c in containers.items() if n not in CANDIDATE_CONTAINERS]

    for container in ordered:
        env = _env_of(container)
        project = _first(env, PROJECT_KEYS)
        database = _first(env, DATABASE_KEYS)
        if project or database:
            return Attribution(
                project=project,
                database=database,
                source=str(container.get("name", "")) or None,
            )
    return None


def merge_attribution(values: list[Attribution | None]) -> Attribution | None:
    """Roll pod-level attribution up to the service that owns those pods.

    Replicas of one service agree, so the common case is a single distinct
    value. They can disagree — a rolling update mid-flight, or two Helm releases
    grouped under one service — and that disagreement is reported rather than
    silently resolved to whichever pod sorted first. A card that confidently
    shows the wrong project is worse than one that says the pods disagree.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None

    projects = {v.project for v in present if v.project}
    databases = {v.database for v in present if v.database}

    return Attribution(
        project=next(iter(projects)) if len(projects) == 1 else None,
        database=next(iter(databases)) if len(databases) == 1 else None,
        source=present[0].source,
        conflict=len(projects) > 1 or len(databases) > 1,
    )

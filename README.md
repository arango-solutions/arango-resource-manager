# Arango Resource Manager

See and safely manage what is running inside an ArangoDB Platform Kubernetes
namespace — what the services are, how long they have been up, what they are
really consuming against what they reserved, and how to scale them down without
breaking the database.

## Why

A Platform namespace accumulates a lot of workloads, and nothing short of
`kubectl` will tell you what is in there. A recorded Platform namespace measured
during design showed the problem plainly:

| | |
|---|---|
| Pods | 59 across ~14 service groups |
| CPU reserved | 46.25 cores |
| CPU actually used | ~0.5 cores — about **1% efficiency** |
| Worst offender | one worker deployment at 25 replicas using ~3m CPU each |
| Containers with no limits | 15 — each able to consume a whole node |

This tool surfaces that, ranks what is reclaimable, and gives you the controls
to act on it.

## Quick start

```bash
make install

cp backend/.env.example backend/.env    # set ARM_KUBE_CONTEXT and ARM_NAMESPACE
make backend                            # http://localhost:8000/docs
make frontend                           # http://localhost:5173
```

`make check` runs ruff, mypy, pytest, the frontend typecheck and the frontend
tests. The default suite runs entirely against recorded fixtures, so it needs
no cluster. HTTP integration tests walk the routes each page actually calls,
including kill/stop/restore through a recording fake client.

To exercise a real cluster, create a throwaway Deployment (never the database)
with `ARM_LIVE_TESTS=1 ARM_READ_ONLY=false` and run
`cd backend && uv run pytest -m live`.

## Layout

| Path | |
|---|---|
| `backend/` | FastAPI + the Kubernetes client, managed with uv |
| `backend/scripts/probe_cluster.py` | read-only probe; `--dump` records test fixtures |
| `frontend/` | Vite + React + Tailwind, avocado palette |

## Safety

The app is read-only by default (`ARM_READ_ONLY=true`), with two further gates
for guarded platform workloads and for the database itself.

Workloads owned by the ArangoDB operator are **protected**. The API refuses core
Kubernetes mutations against them no matter how it is configured, because the
operator would simply reconcile them back — and scaling the database that way
risks the cluster. The Database page edits the `ArangoDeployment` spec instead,
which is the correct path, and it still refuses to touch the agents: agency
quorum means changing the agent count after creation is unsupported.

"Stopping" a service means scaling it to 0 replicas and remembering the previous
count so it can be restored. **Killing** a service does the same, then
force-deletes the current pods so they die immediately instead of waiting out a
graceful shutdown. Deleting a pod is offered too, but it does not stop
anything — the ReplicaSet replaces it within a second, and the UI says so at the
point of decision. Kubernetes cannot stop one container on its own; a container
kill deletes the pod.

## Actions

Each action is planned before it runs:

| | |
|---|---|
| **Scale** | set the replica count |
| **Stop** | scale to 0, recording the previous count first so it can be restored |
| **Kill** | scale to 0 and force-delete the current pods, so the service dies now |
| **Restart** | a rolling replacement, via the pod template annotation |
| **Delete pod** | force-delete one replica — which stops nothing, and the UI says so |

Confirming anything that takes a service to zero requires typing the workload
name. Before any dialog appears, the action runs as a **server-side dry run**:
the real patch with `dryRun=All`, so the API server validates and authorises it
without persisting. An RBAC gap or an admission rejection surfaces before you
are asked to confirm, not after.

The database is resized from its own page, which edits the `ArangoDeployment`
spec. Coordinators and gateways scale freely; shrinking dbservers warns that
the operator must drain shards first; **agents are never scalable** — the
agency is a RAFT quorum and changing its size after creation risks the cluster.

## License

Apache License 2.0. See [LICENSE](LICENSE).

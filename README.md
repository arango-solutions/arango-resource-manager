# Arango Resource Manager

See and safely manage what is running inside an ArangoDB Platform Kubernetes
namespace — what the services are, how long they have been up, what they are
really consuming against what they reserved, and how to scale them down without
breaking the database.

## Why

A Platform namespace accumulates a lot of workloads, and nothing short of
`kubectl` will tell you what is in there. A live namespace measured during
design showed the problem plainly:

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

`make check` runs ruff, mypy, pytest and the frontend typecheck. The test suite
runs entirely against recorded fixtures, so it needs no cluster.

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
count so it can be restored. Deleting a pod is offered too, but it does not stop
anything — the ReplicaSet replaces it within a second, and the UI says so at the
point of decision.

## Status

Phase 0 (scaffold, cluster connection, capability probe) is complete. Inventory,
rollups, events and actions follow; see the plan for the phased build order.

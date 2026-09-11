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

## Recording fixtures without publishing your cluster

The test suite runs against fixtures recorded from a real Platform namespace, and
this repository is public. Both stay true because anonymization happens at record
time and is enforced by the build, not by remembering to clean up afterwards.

`make probe-dump` writes fixtures that carry structure without carrying identity:

| | |
|---|---|
| Environment variables | Dropped, except the two attribution keys — whose **values are pseudonymized** |
| Pod and host IPs | Dropped; nothing in the app reads them |
| Node names, regions, zones | Pseudonymized, because the app does read them |
| Helm chart payloads, `managedFields` | Stripped |

Pseudonyms are deterministic, so distinctness survives: two services on one
database still share a value, two zones remain two zones, and re-recording the
same cluster produces the same names — a `probe-dump` shows an honest diff
instead of churn.

`tests/test_fixture_privacy.py` is the gate. It fails the build on a cloud
hostname, region, availability zone, private address, ARN, instance id or email
reaching a fixture. When it fires, fix the probe so the next recording is clean
at the source — editing the fixture by hand only survives until someone re-records.

Connecting to your own cluster needs no repo changes at all: set
`ARM_KUBECONFIG`, `ARM_KUBE_CONTEXT` and `ARM_NAMESPACE` in `backend/.env`,
which is git-ignored.

## Actions

Four actions, each planned before it runs:

| | |
|---|---|
| **Scale** | set the replica count |
| **Stop** | scale to 0, recording the previous count first so it can be restored |
| **Restart** | a rolling replacement, via the pod template annotation |
| **Delete pod** | evict one replica — which stops nothing, and the UI says so |

Confirming anything that takes a service to zero requires typing the workload
name. Before any dialog appears, the action runs as a **server-side dry run**:
the real patch with `dryRun=All`, so the API server validates and authorises it
without persisting. An RBAC gap or an admission rejection surfaces before you
are asked to confirm, not after.

The database is resized from its own page, which edits the `ArangoDeployment`
spec. Coordinators and gateways scale freely; shrinking dbservers warns that
the operator must drain shards first; **agents are never scalable** — the
agency is a RAFT quorum and changing its size after creation risks the cluster.

## Status

Phases 0–4 are complete: cluster connection, inventory, live usage and the
capacity model, events and logs, and the actions layer.

The actions have been verified against the live cluster in read-only and
dry-run modes — every gate refuses correctly, and the server-side dry runs are
accepted by the API server. The **execute path has not yet been exercised
against a real cluster**; it is covered by unit tests against a fake client
that records what it was asked to do. `ARM_READ_ONLY` remains `true`.

Later: Prometheus history and sparklines, idle-workload detection, right-sizing
recommendations, a PVC panel, and bulk operations.

## License

Apache License 2.0. See [LICENSE](LICENSE).

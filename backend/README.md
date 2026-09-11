# Arango Resource Manager — backend

FastAPI service that reads an ArangoDB Platform Kubernetes namespace and exposes
what is running, what it consumes versus what it has reserved, and the actions
needed to scale it down safely.

## Run

```bash
cp .env.example .env      # then set ARM_KUBE_CONTEXT / ARM_NAMESPACE
make install
make run                  # http://localhost:8000/docs
```

## Safety

`ARM_READ_ONLY=true` is the default and makes every mutating route return 403.
Two further gates sit on top of it:

- `ARM_ALLOW_GUARDED_ACTIONS` — platform infrastructure (the operator, the UI).
- `ARM_ALLOW_DATABASE_SCALING` — the `ArangoDeployment` tier counts.

Workloads owned by the ArangoDB operator are **protected**: the API refuses core
Kubernetes mutations against them regardless of configuration, because the
operator would reconcile them straight back. Resize the database through the
`/api/v1/database` routes, which edit the `ArangoDeployment` spec instead.

## Probe

`make probe` prints the resolved context, namespace and capabilities, then counts
every object it can list. `make probe-dump` additionally records the raw API
responses into `tests/fixtures/`, so the test suite runs with no cluster access.

## Checks

```bash
make check      # ruff + mypy + pytest
```

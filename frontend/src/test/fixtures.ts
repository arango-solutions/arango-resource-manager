import type { ActionPlan, ActionResult, Workload } from '@/lib/schemas'

export const emptyResources = {
  usage: { cpu_cores: 0.01, memory_bytes: 8_000_000 },
  requests: { cpu_cores: 0.25, memory_bytes: 256_000_000 },
  limits: { cpu_cores: 0.25, memory_bytes: 256_000_000 },
  unset_request_containers: 0,
  unset_limit_containers: 0,
  container_count: 1,
}

export const normalWorkload: Workload = {
  kind: 'Deployment',
  name: 'arangodb-file-parser-worker-default',
  service: 'arangodb-file-parser',
  component: 'worker-default',
  match_confidence: 'exact',
  protection: { level: 'normal', reason: null, remediation: null },
  desired_replicas: 5,
  ready_replicas: 5,
  current_replicas: 5,
  chart_version: 'v0.1.3',
  tier: null,
  pod_count: 5,
  resources: emptyResources,
}

export const protectedWorkload: Workload = {
  ...normalWorkload,
  kind: 'ArangoDeployment',
  name: 'dbserver',
  service: 'arangodb-cluster',
  component: 'dbserver',
  protection: {
    level: 'protected',
    reason: 'Managed by the ArangoDB operator.',
    remediation: 'Resize this from the Database page.',
  },
  tier: 'dbservers',
}

export const killPlan: ActionPlan = {
  action: 'kill',
  kind: 'Deployment',
  name: 'arangodb-file-parser-worker-default',
  namespace: 'example-platform',
  current_replicas: 5,
  target_replicas: 0,
  pods_terminating: [{ name: 'worker-a', age_seconds: 120 }],
  frees: { cpu_cores: 1.25, memory_bytes: 1_280_000_000 },
  restore_to: 5,
  protection: { level: 'normal', reason: null, remediation: null },
  server_dry_run: 'accepted',
  requires_typed_confirmation: true,
  warning: 'Pods are force-deleted immediately — no graceful shutdown.',
  force: true,
  targets: [
    {
      kind: 'Deployment',
      name: 'arangodb-file-parser-worker-default',
      current_replicas: 5,
    },
  ],
}

export function okResult(plan: ActionPlan, dryRun: boolean): ActionResult {
  return {
    executed: !dryRun,
    dry_run: dryRun,
    plan,
    blocked_reason: null,
    detail: null,
    remediation: null,
  }
}

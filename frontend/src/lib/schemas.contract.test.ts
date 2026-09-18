import { describe, expect, it } from 'vitest'

import {
  actionResultSchema,
  clusterInfoSchema,
  overviewSchema,
  podDetailSchema,
  serviceDetailSchema,
} from '@/lib/schemas'
import { killPlan, okResult } from '@/test/fixtures'

/**
 * The frontend parses every API payload with these schemas. A backend field
 * rename that still serializes will 200 in pytest and blank a page here.
 */
describe('API contract', () => {
  it('accepts a kill action result the backend actually returns', () => {
    const parsed = actionResultSchema.parse(okResult(killPlan, true))
    expect(parsed.plan?.force).toBe(true)
    expect(parsed.plan?.targets).toHaveLength(1)
  })

  it('accepts the cluster info shape Settings reads', () => {
    clusterInfoSchema.parse({
      namespace: 'example-platform',
      context: 'fixture',
      config_source: 'fixture',
      server_version: '1.31',
      capabilities: { pods_delete: true, metrics_server: true },
      safety: {
        read_only: true,
        allow_guarded_actions: false,
        allow_database_scaling: false,
      },
      budget_mode: 'auto',
    })
  })

  it('accepts an overview the Capacity page can render', () => {
    overviewSchema.parse({
      namespace: 'example-platform',
      captured_at: '2026-09-18T00:00:00+00:00',
      metrics_available: true,
      totals: {
        scope: 'namespace',
        name: 'example-platform',
        title: null,
        resources: {
          usage: { cpu_cores: 0.5, memory_bytes: 1 },
          requests: { cpu_cores: 46.25, memory_bytes: 1 },
          limits: { cpu_cores: 140, memory_bytes: 1 },
          unset_request_containers: 0,
          unset_limit_containers: 15,
          container_count: 59,
        },
        cpu_efficiency: 0.01,
        memory_efficiency: 0.1,
        cpu_overcommit: 3,
        reclaimable_cpu_cores: 45,
        reclaimable_memory_bytes: 1,
        pod_count: 59,
        replicas: 59,
        unset_limit_containers: 15,
        unset_request_containers: 0,
      },
      budget: {
        cpu_cores: 58,
        memory_bytes: 1,
        source: 'derived',
        label: 'derived from requests',
        is_policy: true,
      },
      cpu_budget_used: 0.8,
      memory_budget_used: 0.4,
      service_count: 14,
      services_not_ready: 1,
      workload_count: 20,
      deployment_count: 18,
      statefulset_count: 2,
      pod_count: 59,
      ready_pods: 55,
      pods_without_limits: 15,
      pods_without_limits_actionable: 4,
      pods_with_recent_restarts: 2,
      warning_services: ['arangodb-graphrag-retriever'],
      reclaimable_cost_per_day: null,
      degraded: [],
    })
  })

  it('defaults force and targets when a plan omitted them', () => {
    const stripped = { ...killPlan } as Record<string, unknown>
    delete stripped.force
    delete stripped.targets
    const parsed = actionResultSchema.parse(okResult(stripped as typeof killPlan, true))
    expect(parsed.plan?.force).toBe(false)
    expect(parsed.plan?.targets).toEqual([])
  })

  it('accepts pod and service detail envelopes', () => {
    podDetailSchema.parse({
      name: 'worker-a',
      phase: 'Running',
      ready: true,
      ready_containers: '1/1',
      service: 'arangodb-file-parser',
      workload: { kind: 'Deployment', name: 'arangodb-file-parser-worker-default' },
      protection: { level: 'normal', reason: null, remediation: null },
      node: 'node-a',
      start_time: '2026-09-18T00:00:00+00:00',
      age_seconds: 60,
      ready_since_seconds: 50,
      restart_count: 0,
      last_restart_at: null,
      containers: ['worker'],
      resources: {
        usage: { cpu_cores: 0.01, memory_bytes: 1 },
        requests: { cpu_cores: 0.25, memory_bytes: 1 },
        limits: { cpu_cores: 0.25, memory_bytes: 1 },
        unset_request_containers: 0,
        unset_limit_containers: 0,
        container_count: 1,
      },
      labels: { app: 'worker' },
      container_details: [
        {
          name: 'worker',
          image: 'example/worker:1',
          ready: true,
          restart_count: 0,
          started_at: '2026-09-18T00:00:00+00:00',
          state: 'running',
          last_terminated_reason: null,
          resources: {
            usage: { cpu_cores: null, memory_bytes: null },
            requests: { cpu_cores: 0.25, memory_bytes: 1 },
            limits: { cpu_cores: 0.25, memory_bytes: 1 },
            unset_request_containers: 0,
            unset_limit_containers: 0,
            container_count: 1,
          },
        },
      ],
      conditions: [{ type: 'Ready', status: true, reason: null, message: null }],
    })

    serviceDetailSchema.parse({
      name: 'arangodb-file-parser',
      title: 'File parser',
      source: 'ArangoPlatformService',
      match_confidence: 'exact',
      chart_name: 'arangodb-file-parser',
      chart_version: 'v0.1.3',
      catalog_version: 'v0.1.3',
      version_drift: false,
      ready: true,
      conditions: [],
      route_path: null,
      protection: { level: 'normal', reason: null, remediation: null },
      workload_count: 1,
      pod_count: 1,
      ready_pods: 1,
      desired_replicas: 5,
      instances: ['arangodb-file-parser'],
      resources: {
        usage: { cpu_cores: 0.01, memory_bytes: 1 },
        requests: { cpu_cores: 1.25, memory_bytes: 1 },
        limits: { cpu_cores: 1.25, memory_bytes: 1 },
        unset_request_containers: 0,
        unset_limit_containers: 0,
        container_count: 5,
      },
      warning_count: 0,
      latest_warning: null,
      workloads: [],
      pods: [],
      events: [],
    })
  })
})

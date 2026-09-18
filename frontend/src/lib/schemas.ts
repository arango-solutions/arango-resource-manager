import { z } from 'zod'

/** Parsed at the API boundary so a backend contract change surfaces immediately. */

export const clusterInfoSchema = z.object({
  namespace: z.string(),
  context: z.string(),
  config_source: z.string(),
  server_version: z.string().nullable(),
  capabilities: z.record(z.string(), z.unknown()),
  safety: z.object({
    read_only: z.boolean(),
    allow_guarded_actions: z.boolean(),
    allow_database_scaling: z.boolean(),
  }),
  budget_mode: z.string(),
})

export const protectionSchema = z.object({
  level: z.enum(['protected', 'guarded', 'normal']),
  reason: z.string().nullable(),
  remediation: z.string().nullable(),
})

const resourcesSchema = z.object({
  cpu_cores: z.number().nullable(),
  memory_bytes: z.number().nullable(),
})

export const resourceTripleSchema = z.object({
  usage: resourcesSchema,
  requests: resourcesSchema,
  limits: resourcesSchema,
  unset_request_containers: z.number(),
  unset_limit_containers: z.number(),
  container_count: z.number(),
})

export const conditionSchema = z.object({
  type: z.string(),
  status: z.boolean(),
  reason: z.string().nullable(),
  message: z.string().nullable(),
})

export const eventSchema = z.object({
  type: z.string(),
  reason: z.string().nullable(),
  message: z.string().nullable(),
  count: z.number(),
  last_seen: z.string().nullable(),
  involved_kind: z.string().nullable(),
  involved_name: z.string().nullable(),
})

export const podSchema = z.object({
  name: z.string(),
  phase: z.string(),
  ready: z.boolean(),
  ready_containers: z.string(),
  service: z.string().nullable(),
  workload: z.object({ kind: z.string(), name: z.string() }).nullable(),
  protection: protectionSchema,
  node: z.string().nullable(),
  start_time: z.string().nullable(),
  age_seconds: z.number().nullable(),
  ready_since_seconds: z.number().nullable(),
  restart_count: z.number(),
  last_restart_at: z.string().nullable(),
  containers: z.array(z.string()),
  resources: resourceTripleSchema,
})

export const containerSchema = z.object({
  name: z.string(),
  image: z.string().nullable(),
  ready: z.boolean(),
  restart_count: z.number(),
  started_at: z.string().nullable(),
  state: z.string().nullable(),
  last_terminated_reason: z.string().nullable(),
  resources: resourceTripleSchema,
})

export const podDetailSchema = podSchema.extend({
  labels: z.record(z.string(), z.string()),
  container_details: z.array(containerSchema),
  conditions: z.array(conditionSchema),
})

export const workloadSchema = z.object({
  kind: z.string(),
  name: z.string(),
  service: z.string().nullable(),
  component: z.string().nullable(),
  match_confidence: z.string().nullable(),
  protection: protectionSchema,
  desired_replicas: z.number(),
  ready_replicas: z.number(),
  current_replicas: z.number(),
  chart_version: z.string().nullable(),
  tier: z.string().nullable(),
  pod_count: z.number(),
  resources: resourceTripleSchema,
})

export const serviceSchema = z.object({
  name: z.string(),
  title: z.string(),
  source: z.string(),
  match_confidence: z.string().nullable(),
  chart_name: z.string().nullable(),
  chart_version: z.string().nullable(),
  catalog_version: z.string().nullable(),
  version_drift: z.boolean(),
  ready: z.boolean().nullable(),
  conditions: z.array(conditionSchema),
  route_path: z.string().nullable(),
  protection: protectionSchema,
  workload_count: z.number(),
  pod_count: z.number(),
  ready_pods: z.number(),
  desired_replicas: z.number(),
  instances: z.array(z.string()),
  resources: resourceTripleSchema,
  warning_count: z.number(),
  latest_warning: z.string().nullable(),
})

export const serviceDetailSchema = serviceSchema.extend({
  workloads: z.array(workloadSchema),
  pods: z.array(podSchema),
  events: z.array(eventSchema),
})

export const genAiComponentSchema = z.object({
  role: z.enum(['project', 'retriever', 'importer']),
  kind: z.string(),
  name: z.string(),
  service: z.string().nullable(),
  route_path: z.string().nullable(),
  chart_version: z.string().nullable(),
  desired_replicas: z.number(),
  ready_replicas: z.number(),
  pod_count: z.number(),
  ready_pods: z.number(),
  age_seconds: z.number().nullable(),
  restart_count: z.number(),
  chat_model: z.string().nullable(),
  embedding_model: z.string().nullable(),
  protection: protectionSchema,
  resources: resourceTripleSchema,
  warning_count: z.number(),
})

export const genAiProjectSchema = z.object({
  key: z.string(),
  project_name: z.string().nullable(),
  db_name: z.string().nullable(),
  status: z.enum(['paired', 'project_only', 'retriever_only', 'unidentified']),
  project: genAiComponentSchema.nullable(),
  retrievers: z.array(genAiComponentSchema),
  others: z.array(genAiComponentSchema),
  resources: resourceTripleSchema,
  warning_count: z.number(),
})

export const budgetSchema = z.object({
  cpu_cores: z.number().nullable(),
  memory_bytes: z.number().nullable(),
  source: z.enum(['quota', 'configured', 'derived']),
  label: z.string(),
  is_policy: z.boolean(),
})

export const resourceReportSchema = z.object({
  scope: z.string(),
  name: z.string(),
  title: z.string().nullable(),
  resources: resourceTripleSchema,
  cpu_efficiency: z.number().nullable(),
  memory_efficiency: z.number().nullable(),
  cpu_overcommit: z.number().nullable(),
  reclaimable_cpu_cores: z.number().nullable(),
  reclaimable_memory_bytes: z.number().nullable(),
  pod_count: z.number(),
  replicas: z.number(),
  unset_limit_containers: z.number(),
  unset_request_containers: z.number(),
})

export const overviewSchema = z.object({
  namespace: z.string(),
  captured_at: z.string(),
  metrics_available: z.boolean(),
  totals: resourceReportSchema,
  budget: budgetSchema,
  cpu_budget_used: z.number().nullable(),
  memory_budget_used: z.number().nullable(),
  service_count: z.number(),
  services_not_ready: z.number(),
  workload_count: z.number(),
  deployment_count: z.number(),
  statefulset_count: z.number(),
  pod_count: z.number(),
  ready_pods: z.number(),
  pods_without_limits: z.number(),
  pods_without_limits_actionable: z.number(),
  pods_with_recent_restarts: z.number(),
  warning_services: z.array(z.string()),
  reclaimable_cost_per_day: z.number().nullable(),
  degraded: z.array(z.string()),
})

export const wasteSchema = z.object({
  kind: z.string(),
  name: z.string(),
  service: z.string().nullable(),
  protection: protectionSchema,
  replicas: z.number(),
  pod_count: z.number(),
  resources: resourceTripleSchema,
  cpu_efficiency: z.number().nullable(),
  memory_efficiency: z.number().nullable(),
  reclaimable_cpu_cores: z.number(),
  reclaimable_memory_bytes: z.number(),
  cost_per_day: z.number().nullable(),
})

export const unboundedSchema = z.object({
  name: z.string(),
  service: z.string().nullable(),
  workload: z.string().nullable(),
  protection: protectionSchema,
  unset_limit_containers: z.number(),
  container_count: z.number(),
  cpu_usage: z.number().nullable(),
  memory_usage: z.number().nullable(),
})

const resourcesOnlySchema = z.object({
  cpu_cores: z.number().nullable(),
  memory_bytes: z.number().nullable(),
})

export const actionPlanSchema = z.object({
  action: z.string(),
  kind: z.string(),
  name: z.string(),
  namespace: z.string(),
  current_replicas: z.number().nullable(),
  target_replicas: z.number().nullable(),
  pods_terminating: z.array(
    z.object({ name: z.string(), age_seconds: z.number().nullable() }),
  ),
  frees: resourcesOnlySchema,
  restore_to: z.number().nullable(),
  protection: protectionSchema,
  server_dry_run: z.string().nullable(),
  requires_typed_confirmation: z.boolean(),
  warning: z.string().nullable(),
  force: z.boolean(),
  targets: z.array(
    z.object({
      kind: z.string(),
      name: z.string(),
      current_replicas: z.number(),
    }),
  ),
})

export const actionResultSchema = z.object({
  executed: z.boolean(),
  dry_run: z.boolean(),
  plan: actionPlanSchema.nullable(),
  blocked_reason: z.string().nullable(),
  detail: z.string().nullable(),
  remediation: z.string().nullable(),
})

export const actionRecordSchema = z.object({
  ts: z.string(),
  action: z.string(),
  kind: z.string().nullable(),
  name: z.string().nullable(),
  from_replicas: z.number().nullable(),
  to_replicas: z.number().nullable(),
  dry_run: z.boolean(),
  result: z.string(),
  detail: z.string().nullable(),
})

export const tierSchema = z.object({
  name: z.string(),
  count: z.number(),
  ready: z.number(),
  policy: z.string(),
  scalable: z.boolean(),
  note: z.string(),
})

export const databaseStatusSchema = z.object({
  name: z.string(),
  mode: z.string().nullable(),
  ready: z.boolean().nullable(),
  scaling_enabled: z.boolean(),
  tiers: z.array(tierSchema),
  conditions: z.array(conditionSchema),
})

export const stoppedSchema = z.record(
  z.string(),
  z.object({
    previous_replicas: z.number(),
    stopped_at: z.string(),
    actor: z.string(),
  }),
)

export type ActionPlan = z.infer<typeof actionPlanSchema>
export type ActionResult = z.infer<typeof actionResultSchema>
export type ActionRecord = z.infer<typeof actionRecordSchema>
export type Tier = z.infer<typeof tierSchema>
export type DatabaseStatus = z.infer<typeof databaseStatusSchema>
export type Stopped = z.infer<typeof stoppedSchema>
export type Budget = z.infer<typeof budgetSchema>
export type ResourceReport = z.infer<typeof resourceReportSchema>
export type Overview = z.infer<typeof overviewSchema>
export type Waste = z.infer<typeof wasteSchema>
export type Unbounded = z.infer<typeof unboundedSchema>
export type ClusterInfo = z.infer<typeof clusterInfoSchema>
export type Protection = z.infer<typeof protectionSchema>
export type ResourceTriple = z.infer<typeof resourceTripleSchema>
export type Condition = z.infer<typeof conditionSchema>
export type EventItem = z.infer<typeof eventSchema>
export type GenAiComponent = z.infer<typeof genAiComponentSchema>
export type GenAiProject = z.infer<typeof genAiProjectSchema>
export type Pod = z.infer<typeof podSchema>
export type PodDetail = z.infer<typeof podDetailSchema>
export type Workload = z.infer<typeof workloadSchema>
export type Service = z.infer<typeof serviceSchema>
export type ServiceDetail = z.infer<typeof serviceDetailSchema>

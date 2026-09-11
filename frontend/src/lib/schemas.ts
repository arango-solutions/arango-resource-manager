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

export type ClusterInfo = z.infer<typeof clusterInfoSchema>
export type Protection = z.infer<typeof protectionSchema>
export type ResourceTriple = z.infer<typeof resourceTripleSchema>
export type Condition = z.infer<typeof conditionSchema>
export type EventItem = z.infer<typeof eventSchema>
export type Pod = z.infer<typeof podSchema>
export type PodDetail = z.infer<typeof podDetailSchema>
export type Workload = z.infer<typeof workloadSchema>
export type Service = z.infer<typeof serviceSchema>
export type ServiceDetail = z.infer<typeof serviceDetailSchema>

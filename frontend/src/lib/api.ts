import axios from 'axios'
import type { ZodType } from 'zod'

import {
  actionRecordSchema,
  actionResultSchema,
  clusterInfoSchema,
  databaseStatusSchema,
  eventSchema,
  genAiProjectSchema,
  stoppedSchema,
  overviewSchema,
  resourceReportSchema,
  unboundedSchema,
  wasteSchema,
  podDetailSchema,
  podSchema,
  serviceDetailSchema,
  serviceSchema,
  workloadSchema,
  type ClusterInfo,
  type GenAiProject,
  type Pod,
  type PodDetail,
  type Overview,
  type ResourceReport,
  type Service,
  type ServiceDetail,
  type Unbounded,
  type Waste,
  type Workload,
} from './schemas'
import { z } from 'zod'

export const http = axios.create({ baseURL: '/api/v1', timeout: 30_000 })

async function get<T>(path: string, schema: ZodType<T>, params?: object): Promise<T> {
  const { data } = await http.get(path, { params })
  return schema.parse(data)
}

export function fetchClusterInfo(): Promise<ClusterInfo> {
  return get('/cluster/info', clusterInfoSchema)
}

export function fetchServices(): Promise<Service[]> {
  return get('/services', z.array(serviceSchema))
}

export function fetchService(name: string): Promise<ServiceDetail> {
  return get(`/services/${encodeURIComponent(name)}`, serviceDetailSchema)
}

export function fetchWorkloads(params?: { service?: string }): Promise<Workload[]> {
  return get('/workloads', z.array(workloadSchema), params)
}

export interface PodQuery {
  service?: string
  workload?: string
  phase?: string
  sort?: 'name' | 'uptime' | 'restarts' | 'cpu' | 'memory'
  order?: 'asc' | 'desc'
}

export function fetchPods(params?: PodQuery): Promise<Pod[]> {
  return get('/pods', z.array(podSchema), params)
}

export function fetchPod(name: string): Promise<PodDetail> {
  return get(`/pods/${encodeURIComponent(name)}`, podDetailSchema)
}

export function fetchGenAiProjects(): Promise<GenAiProject[]> {
  return get('/genai/projects', z.array(genAiProjectSchema))
}

export function fetchOverview(): Promise<Overview> {
  return get('/namespace/overview', overviewSchema)
}

export function fetchWaste(limit = 20): Promise<Waste[]> {
  return get('/resources/waste', z.array(wasteSchema), { limit })
}

export function fetchUnbounded(): Promise<Unbounded[]> {
  return get('/resources/unbounded', z.array(unboundedSchema))
}

export function fetchRollup(scope: 'namespace' | 'service' | 'workload'): Promise<ResourceReport[]> {
  return get('/resources/rollup', z.array(resourceReportSchema), { scope })
}

export function fetchEvents(params?: { service?: string; involved?: string; limit?: number }) {
  return get('/events', z.array(eventSchema), params)
}

export interface LogQuery {
  container?: string
  tailLines?: number
  previous?: boolean
}

/** Logs are plain text, so they bypass the zod boundary the JSON routes use. */
export async function fetchPodLogs(name: string, query: LogQuery = {}): Promise<string> {
  const { data } = await http.get(`/pods/${encodeURIComponent(name)}/logs`, {
    params: {
      container: query.container,
      tail_lines: query.tailLines ?? 200,
      previous: query.previous ?? false,
    },
    responseType: 'text',
    transformResponse: (value) => value,
  })
  return String(data)
}

// -- actions ---------------------------------------------------------------

/**
 * A refusal is a normal outcome here, not an exception: the backend returns a
 * structured reason and a remediation with a 4xx status. Unwrapping it means
 * the UI can explain why rather than showing "request failed".
 */
async function post<T>(path: string, body: unknown, schema: ZodType<T>): Promise<T> {
  try {
    const { data } = await http.post(path, body)
    return schema.parse(data)
  } catch (error) {
    const payload = (error as { response?: { data?: unknown } })?.response?.data
    const parsed = schema.safeParse(payload)
    if (parsed.success) return parsed.data
    throw error
  }
}

export interface ScaleArgs {
  kind: string
  name: string
  replicas: number
  dryRun: boolean
}

export function scaleWorkload({ kind, name, replicas, dryRun }: ScaleArgs) {
  return post('/actions/scale', { kind, name, replicas, dry_run: dryRun }, actionResultSchema)
}

export function stopWorkload(kind: string, name: string, dryRun: boolean) {
  return post('/actions/stop', { kind, name, dry_run: dryRun }, actionResultSchema)
}

export function restoreWorkload(kind: string, name: string, dryRun: boolean) {
  return post('/actions/restore', { kind, name, dry_run: dryRun }, actionResultSchema)
}

export function restartWorkload(kind: string, name: string, dryRun: boolean) {
  return post('/actions/restart', { kind, name, dry_run: dryRun }, actionResultSchema)
}

export function deletePod(name: string, dryRun: boolean) {
  return post(
    `/actions/pods/${encodeURIComponent(name)}/delete`,
    { dry_run: dryRun },
    actionResultSchema,
  )
}

export function fetchStopped() {
  return get('/actions/stopped', stoppedSchema)
}

export function fetchHistory(limit = 100) {
  return get('/actions/history', z.array(actionRecordSchema), { limit })
}

export function fetchDatabase() {
  return get('/database', databaseStatusSchema)
}

export function scaleDatabase(tier: string, count: number, dryRun: boolean) {
  return post('/database/scale', { tier, count, dry_run: dryRun }, actionResultSchema)
}

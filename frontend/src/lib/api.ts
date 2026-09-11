import axios from 'axios'
import type { ZodType } from 'zod'

import {
  clusterInfoSchema,
  eventSchema,
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

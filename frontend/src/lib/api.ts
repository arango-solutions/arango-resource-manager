import axios from 'axios'
import type { ZodType } from 'zod'

import {
  clusterInfoSchema,
  podDetailSchema,
  podSchema,
  serviceDetailSchema,
  serviceSchema,
  workloadSchema,
  type ClusterInfo,
  type Pod,
  type PodDetail,
  type Service,
  type ServiceDetail,
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

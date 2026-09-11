import axios from 'axios'
import type { ZodType } from 'zod'

import { clusterInfoSchema, type ClusterInfo } from './schemas'

export const http = axios.create({ baseURL: '/api/v1', timeout: 30_000 })

async function get<T>(path: string, schema: ZodType<T>): Promise<T> {
  const { data } = await http.get(path)
  return schema.parse(data)
}

export function fetchClusterInfo(): Promise<ClusterInfo> {
  return get('/cluster/info', clusterInfoSchema)
}

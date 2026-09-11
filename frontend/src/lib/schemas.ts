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

export type ClusterInfo = z.infer<typeof clusterInfoSchema>

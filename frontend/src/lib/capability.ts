import type { ClusterInfo } from './schemas'

export type ChipTone = 'ok' | 'off' | 'warn'

export interface Chip {
  label: string
  tone: ChipTone
  title: string
}

/**
 * Turn the backend capability probe into chips. A user on a namespace where
 * something is missing should see *why* a panel is empty, not a blank card.
 */
export function capabilityChips(info: ClusterInfo): Chip[] {
  const caps = info.capabilities
  const has = (key: string) => caps[key] === true

  const chips: Chip[] = [
    {
      label: has('metrics_server') ? 'metrics' : 'no metrics',
      tone: has('metrics_server') ? 'ok' : 'warn',
      title: has('metrics_server')
        ? 'metrics-server is serving live CPU and memory usage.'
        : 'metrics-server is unavailable, so live usage cannot be shown.',
    },
    {
      label: caps.resourcequota_present ? 'quota' : 'no quota',
      tone: caps.resourcequota_present ? 'ok' : 'off',
      title: caps.resourcequota_present
        ? 'A ResourceQuota defines this namespace’s ceiling.'
        : 'No ResourceQuota exists, so the budget is derived from requests.',
    },
    {
      label: has('nodes_list') ? 'nodes' : 'namespace-scoped',
      tone: has('nodes_list') ? 'ok' : 'off',
      title: has('nodes_list')
        ? 'Node capacity is readable.'
        : 'This credential cannot read nodes, so cluster headroom is not shown.',
    },
  ]

  if (info.safety.read_only) {
    chips.push({
      label: 'read-only',
      tone: 'warn',
      title: 'ARM_READ_ONLY is set. Every mutating route returns 403.',
    })
  }

  return chips
}

import { ArrowDown, ArrowUp } from 'lucide-react'
import { Link } from 'react-router-dom'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import type { PodQuery } from '@/lib/api'
import { formatCpu, formatMemory } from '@/lib/format'
import type { Pod } from '@/lib/schemas'
import PodStatusPill from './PodStatusPill'
import RestartBadge from './RestartBadge'
import UptimeCell from './UptimeCell'

type SortKey = NonNullable<PodQuery['sort']>

interface Props {
  pods: Pod[]
  sort: SortKey
  order: 'asc' | 'desc'
  onSort: (key: SortKey) => void
  showService?: boolean
}

const HEADERS: { key: SortKey | null; label: string; align?: string }[] = [
  { key: null, label: 'Status' },
  { key: 'name', label: 'Pod' },
  { key: null, label: 'Workload' },
  { key: 'uptime', label: 'Uptime' },
  { key: 'restarts', label: 'Restarts' },
  { key: 'cpu', label: 'CPU used / reserved', align: 'text-right' },
  { key: 'memory', label: 'Memory used / reserved', align: 'text-right' },
]

export default function PodTable({ pods, sort, order, onSort, showService = true }: Props) {
  return (
    // Wide tables scroll inside their own container; the page never scrolls
    // sideways.
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[56rem] border-collapse bg-cream text-sm">
        <thead>
          <tr className="border-b border-line bg-panel text-left">
            {HEADERS.filter((h) => showService || h.label !== 'Workload').map((header) => (
              <th
                key={header.label}
                className={`px-3 py-2 text-xs font-medium text-muted ${header.align ?? ''}`}
              >
                {header.key ? (
                  <button
                    type="button"
                    onClick={() => onSort(header.key as SortKey)}
                    className="inline-flex items-center gap-1 hover:text-body"
                  >
                    {header.label}
                    {sort === header.key &&
                      (order === 'asc' ? (
                        <ArrowUp size={11} aria-hidden />
                      ) : (
                        <ArrowDown size={11} aria-hidden />
                      ))}
                  </button>
                ) : (
                  header.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pods.map((pod) => (
            <tr key={pod.name} className="border-b border-line/60 last:border-0 hover:bg-panel/60">
              <td className="px-3 py-2">
                <PodStatusPill
                  phase={pod.phase}
                  ready={pod.ready}
                  readyContainers={pod.ready_containers}
                />
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs break-all text-body">{pod.name}</span>
                  <ProtectedBadge protection={pod.protection} />
                </div>
                {showService && pod.service && (
                  <Link
                    to={`/services/${encodeURIComponent(pod.service)}`}
                    className="text-[11px] text-muted hover:text-arango hover:underline"
                  >
                    {pod.service}
                  </Link>
                )}
              </td>
              {showService && (
                <td className="px-3 py-2 font-mono text-xs text-muted">
                  {pod.workload?.name ?? '—'}
                </td>
              )}
              <td className="px-3 py-2">
                <UptimeCell seconds={pod.age_seconds} startedAt={pod.start_time} />
              </td>
              <td className="px-3 py-2">
                <RestartBadge count={pod.restart_count} lastRestartAt={pod.last_restart_at} />
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs">
                <span className="text-body">{formatCpu(pod.resources.usage.cpu_cores)}</span>
                <span className="text-muted"> / {formatCpu(pod.resources.requests.cpu_cores)}</span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs">
                <span className="text-body">{formatMemory(pod.resources.usage.memory_bytes)}</span>
                <span className="text-muted">
                  {' '}
                  / {formatMemory(pod.resources.requests.memory_bytes)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

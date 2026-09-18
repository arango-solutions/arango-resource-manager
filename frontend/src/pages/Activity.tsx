import { useQuery } from '@tanstack/react-query'

import Badge from '@/components/ui/Badge'
import EmptyState from '@/components/ui/EmptyState'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchHistory } from '@/lib/api'

const LABELS: Record<string, string> = {
  scale: 'Scaled',
  stop: 'Stopped',
  restore: 'Restored',
  restart: 'Restarted',
  delete_pod: 'Deleted pod',
  kill: 'Killed',
  kill_service: 'Killed service',
  database_scale: 'Resized database',
}

export default function Activity() {
  const { data, error, isPending } = useQuery({
    queryKey: ['actions', 'history'],
    queryFn: () => fetchHistory(100),
    refetchInterval: 15_000,
  })

  if (isPending) return <Spinner />
  if (error) return <ErrorPanel title="Could not read the action log" error={error} />

  if (data.length === 0) {
    return (
      <EmptyState
        title="Nothing has been changed through this tool yet."
        hint="Every scale, stop, restart and delete is recorded here, including the ones that were refused."
      />
    )
  }

  return (
    <div className="space-y-3">
      <header>
        <h2 className="text-sm font-semibold text-body">Activity</h2>
        <p className="text-xs text-muted">
          Append-only. Dry runs are not recorded — nothing changed.
        </p>
      </header>

      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-cream">
        {data.map((entry, index) => (
          <li key={`${entry.ts}-${index}`} className="flex flex-wrap items-center gap-2 px-3 py-2">
            <Badge tone={entry.result === 'ok' ? 'good' : 'bad'}>
              {LABELS[entry.action] ?? entry.action}
            </Badge>
            <span className="font-mono text-xs break-all text-body">{entry.name}</span>
            {entry.from_replicas !== null && entry.to_replicas !== null && (
              <span className="font-mono text-[11px] text-muted">
                {entry.from_replicas} → {entry.to_replicas}
              </span>
            )}
            <time className="ml-auto font-mono text-[11px] text-muted" dateTime={entry.ts}>
              {new Date(entry.ts).toLocaleString()}
            </time>
            {entry.detail && (
              <p className="w-full font-mono text-[11px] text-danger">{entry.detail}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

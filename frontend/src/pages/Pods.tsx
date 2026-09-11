import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import PodTable from '@/components/pods/PodTable'
import EmptyState from '@/components/ui/EmptyState'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchPods, type PodQuery } from '@/lib/api'

type SortKey = NonNullable<PodQuery['sort']>

export default function Pods() {
  const [sort, setSort] = useState<SortKey>('uptime')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')

  const { data, error, isPending } = useQuery({
    queryKey: ['pods', { sort, order }],
    queryFn: () => fetchPods({ sort, order }),
    refetchInterval: 10_000,
  })

  function handleSort(key: SortKey) {
    if (key === sort) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(key)
      setOrder(key === 'name' ? 'asc' : 'desc')
    }
  }

  if (isPending) return <Spinner label="Reading pods…" />
  if (error) return <ErrorPanel title="Could not list pods" error={error} />

  const restarting = data.filter((p) => p.restart_count > 0).length
  const notReady = data.filter((p) => !p.ready).length

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-sm font-semibold text-body">Pods</h2>
        <p className="text-xs text-muted">
          {data.length} running
          {notReady > 0 && <span className="text-pit"> · {notReady} not ready</span>}
          {restarting > 0 && <span> · {restarting} with restarts</span>}
        </p>
      </header>

      {data.length === 0 ? (
        <EmptyState title="No pods in this namespace." />
      ) : (
        <PodTable pods={data} sort={sort} order={order} onSort={handleSort} />
      )}
    </div>
  )
}

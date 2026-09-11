import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import EventFeed from '@/components/events/EventFeed'
import PodDrawer from '@/components/pods/PodDrawer'
import PodTable from '@/components/pods/PodTable'
import ConditionList from '@/components/services/ConditionList'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchService } from '@/lib/api'
import { formatCpu, formatMemory } from '@/lib/format'
import type { Workload } from '@/lib/schemas'

export default function ServiceDetail() {
  const { name = '' } = useParams()
  const [selectedPod, setSelectedPod] = useState<string | null>(null)
  const { data, error, isPending } = useQuery({
    queryKey: ['services', name],
    queryFn: () => fetchService(name),
    refetchInterval: 10_000,
  })

  if (isPending) return <Spinner label={`Reading ${name}…`} />
  if (error) return <ErrorPanel title={`Could not read ${name}`} error={error} />

  return (
    <div className="space-y-5">
      <Link
        to="/services"
        className="inline-flex items-center gap-1 text-xs text-muted hover:text-arango"
      >
        <ArrowLeft size={12} aria-hidden />
        All services
      </Link>

      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-body">{data.title}</h2>
        <Badge tone={data.ready === false ? 'bad' : data.ready ? 'good' : 'neutral'}>
          {data.ready === null ? 'unknown' : data.ready ? 'ready' : 'not ready'}
        </Badge>
        <ProtectedBadge protection={data.protection} />
        {data.chart_version && (
          <Badge tone="neutral" mono title={data.chart_name ?? undefined}>
            {data.chart_version}
          </Badge>
        )}
        {data.route_path && (
          <a
            href={data.route_path}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono text-xs text-arango hover:underline"
          >
            <ExternalLink size={11} aria-hidden />
            {data.route_path}
          </a>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold text-body">Status</h3>
          <ConditionList conditions={data.conditions} />
        </Card>

        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold text-body">
            Warnings
            {data.warning_count > 0 && (
              <span className="ml-2 text-xs font-normal text-pit">{data.warning_count}</span>
            )}
          </h3>
          {/* Conditions name the failed check; the events say what went wrong. */}
          <EventFeed events={data.events.slice(0, 4)} />
        </Card>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-body">
          Workloads <span className="text-xs font-normal text-muted">{data.workload_count}</span>
        </h3>
        {data.workloads.length === 0 ? (
          <p className="rounded-lg border border-dashed border-line bg-panel/60 px-4 py-6 text-center text-xs text-muted">
            This service is declared but nothing is running under it — see the warnings above.
          </p>
        ) : (
          <WorkloadTable workloads={data.workloads} />
        )}
      </section>

      {data.pods.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-body">
            Pods <span className="text-xs font-normal text-muted">{data.pods.length}</span>
          </h3>
          <PodTable
            pods={data.pods}
            sort="name"
            order="asc"
            onSort={() => undefined}
            showService={false}
            onSelect={setSelectedPod}
          />
        </section>
      )}

      {selectedPod && <PodDrawer name={selectedPod} onClose={() => setSelectedPod(null)} />}
    </div>
  )
}

function WorkloadTable({ workloads }: { workloads: Workload[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[44rem] border-collapse bg-cream text-sm">
        <thead>
          <tr className="border-b border-line bg-panel text-left text-xs text-muted">
            <th className="px-3 py-2 font-medium">Workload</th>
            <th className="px-3 py-2 font-medium">Kind</th>
            <th className="px-3 py-2 font-medium">Replicas</th>
            <th className="px-3 py-2 text-right font-medium">CPU used / reserved</th>
            <th className="px-3 py-2 text-right font-medium">Memory used / reserved</th>
          </tr>
        </thead>
        <tbody>
          {workloads.map((workload) => (
            <tr key={`${workload.kind}-${workload.name}`} className="border-b border-line/60 last:border-0">
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs break-all text-body">{workload.name}</span>
                  <ProtectedBadge protection={workload.protection} />
                </div>
                {workload.component && (
                  <span className="text-[11px] text-muted">{workload.component}</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs text-muted">
                {workload.kind}
                {workload.tier && <span className="font-mono"> · {workload.tier}</span>}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-body">
                {workload.ready_replicas}/{workload.desired_replicas}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs">
                <span className="text-body">{formatCpu(workload.resources.usage.cpu_cores)}</span>
                <span className="text-muted">
                  {' '}
                  / {formatCpu(workload.resources.requests.cpu_cores)}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs">
                <span className="text-body">
                  {formatMemory(workload.resources.usage.memory_bytes)}
                </span>
                <span className="text-muted">
                  {' '}
                  / {formatMemory(workload.resources.requests.memory_bytes)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

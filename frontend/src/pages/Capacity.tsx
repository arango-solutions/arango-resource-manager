import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import CapacityBar from '@/components/resources/CapacityBar'
import EfficiencyPill from '@/components/resources/EfficiencyPill'
import StatTile from '@/components/resources/StatTile'
import Card from '@/components/ui/Card'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchOverview, fetchUnbounded, fetchWaste } from '@/lib/api'
import { formatCpu, formatMemory, formatPercent } from '@/lib/format'

export default function Capacity() {
  const overview = useQuery({
    queryKey: ['namespace', 'overview'],
    queryFn: fetchOverview,
    refetchInterval: 15_000,
  })
  const waste = useQuery({
    queryKey: ['resources', 'waste', 20],
    queryFn: () => fetchWaste(20),
    refetchInterval: 15_000,
  })
  const unbounded = useQuery({
    queryKey: ['resources', 'unbounded'],
    queryFn: fetchUnbounded,
    refetchInterval: 30_000,
  })

  if (overview.isPending) return <Spinner label="Measuring the namespace…" />
  if (overview.error) return <ErrorPanel title="Could not read capacity" error={overview.error} />

  const data = overview.data
  const r = data.totals.resources
  const actionable = (unbounded.data ?? []).filter((p) => p.protection.level !== 'protected')
  const operatorOwned = (unbounded.data ?? []).length - actionable.length

  return (
    <div className="space-y-6">
      <Card className="p-4">
        <h2 className="text-sm font-semibold text-body">What "provisioned" means here</h2>
        {/* Being straight about this is the whole integrity of the page. */}
        <p className="mt-1 max-w-prose text-xs text-muted">
          Used, reserved and limit are measured facts. The budget is a number someone chose —{' '}
          <span className="font-mono text-body">{data.budget.label}</span>. This credential is
          scoped to the namespace and cannot read node capacity, so nothing here is a reading of
          how much room the cluster actually has.
        </p>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Overcommit"
          value={data.totals.cpu_overcommit ? `${data.totals.cpu_overcommit.toFixed(2)}×` : '—'}
          sub={`limits ${formatCpu(r.limits.cpu_cores)} vs ${formatCpu(r.requests.cpu_cores)} reserved`}
          footer="If everything burst at once, this namespace would need the limit figure."
        />
        <StatTile
          label="Unbounded pods"
          value={String(actionable.length)}
          sub="no CPU or memory limit set"
          tone={actionable.length > 0 ? 'attention' : 'default'}
          footer={
            operatorOwned > 0
              ? `${operatorOwned} more belong to the database, where the operator omits limits deliberately.`
              : undefined
          }
        />
        <StatTile
          label="Reclaimable CPU"
          value={formatCpu(data.totals.reclaimable_cpu_cores)}
          unit="cores"
          sub={`across ${waste.data?.length ?? 0} workloads`}
          tone="attention"
        />
        <StatTile
          label="Reclaimable memory"
          value={formatMemory(data.totals.reclaimable_memory_bytes)}
          sub="reserved but unused"
          tone="attention"
        />
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-body">Namespace</h2>
        <Card className="space-y-4 p-4">
          <CapacityBar
            label="CPU"
            used={r.usage.cpu_cores}
            reserved={r.requests.cpu_cores}
            limit={r.limits.cpu_cores}
            budget={data.budget.cpu_cores}
            format={formatCpu}
          />
          <CapacityBar
            label="Memory"
            used={r.usage.memory_bytes}
            reserved={r.requests.memory_bytes}
            limit={r.limits.memory_bytes}
            budget={data.budget.memory_bytes}
            format={formatMemory}
          />
        </Card>
      </section>

      <section>
        <header className="mb-2 flex items-baseline gap-3">
          <h2 className="text-sm font-semibold text-body">Most reclaimable</h2>
          <p className="text-xs text-muted">
            Workloads reserving materially more than they use, worst first
          </p>
        </header>
        {waste.data && waste.data.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[54rem] border-collapse bg-cream text-sm">
              <thead>
                <tr className="border-b border-line bg-panel text-left text-xs text-muted">
                  <th className="px-3 py-2 font-medium">Workload</th>
                  <th className="px-3 py-2 font-medium">Service</th>
                  <th className="px-3 py-2 text-right font-medium">Replicas</th>
                  <th className="px-3 py-2 text-right font-medium">Used</th>
                  <th className="px-3 py-2 text-right font-medium">Reserved</th>
                  <th className="px-3 py-2 text-right font-medium">Efficiency</th>
                  <th className="px-3 py-2 text-right font-medium">Reclaimable</th>
                </tr>
              </thead>
              <tbody>
                {waste.data.map((item) => (
                  <tr key={item.name} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs break-all text-body">{item.name}</span>
                        <ProtectedBadge protection={item.protection} />
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {item.service ? (
                        <Link
                          to={`/services/${encodeURIComponent(item.service)}`}
                          className="text-muted hover:text-arango hover:underline"
                        >
                          {item.service}
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-body">
                      {item.replicas}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-body">
                      {formatCpu(item.resources.usage.cpu_cores)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-muted">
                      {formatCpu(item.resources.requests.cpu_cores)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <EfficiencyPill value={item.cpu_efficiency} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs font-semibold text-pit">
                      {formatCpu(item.reclaimable_cpu_cores)}
                      {item.cost_per_day !== null && (
                        <span className="block text-[10px] font-normal text-muted">
                          ${item.cost_per_day.toFixed(2)}/day
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-muted">
            Nothing is materially over-reserved
            {!data.metrics_available && ' — but usage is unknown, so this cannot be judged'}.
          </p>
        )}
      </section>

      {actionable.length > 0 && (
        <section>
          <header className="mb-2">
            <h2 className="text-sm font-semibold text-body">No limits set</h2>
            <p className="text-xs text-muted">
              A container with no limit can consume an entire node.
            </p>
          </header>
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-cream">
            {actionable.map((pod) => (
              <li key={pod.name} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1 font-mono text-xs break-all text-body">
                  {pod.name}
                </span>
                <span className="text-[11px] text-muted">
                  {pod.unset_limit_containers}/{pod.container_count} containers
                </span>
                <span className="font-mono text-[11px] text-muted">
                  {formatCpu(pod.cpu_usage)} · {formatMemory(pod.memory_usage)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-body">Efficiency by service</h2>
        <ServiceEfficiency />
      </section>
    </div>
  )
}

function ServiceEfficiency() {
  const { data } = useQuery({
    queryKey: ['resources', 'rollup', 'service'],
    queryFn: () => import('@/lib/api').then((m) => m.fetchRollup('service')),
    refetchInterval: 15_000,
  })

  if (!data) return <Spinner />

  const sorted = [...data].sort(
    (a, b) => (b.resources.requests.cpu_cores ?? 0) - (a.resources.requests.cpu_cores ?? 0),
  )

  return (
    <div className="space-y-3">
      {sorted.map((report) => (
        <div key={report.name} className="rounded-lg border border-line bg-panel p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <Link
              to={`/services/${encodeURIComponent(report.name)}`}
              className="min-w-0 flex-1 truncate text-xs font-medium text-body hover:text-arango"
            >
              {report.title ?? report.name}
            </Link>
            <span className="text-[11px] text-muted">
              {formatPercent(report.cpu_efficiency)} of CPU used
            </span>
          </div>
          <CapacityBar
            label={`${report.name} CPU`}
            used={report.resources.usage.cpu_cores}
            reserved={report.resources.requests.cpu_cores}
            limit={report.resources.limits.cpu_cores}
            budget={null}
            format={formatCpu}
          />
        </div>
      ))}
    </div>
  )
}

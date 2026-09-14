import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import CapacityBar from '@/components/resources/CapacityBar'
import DualBar from '@/components/resources/DualBar'
import StatTile from '@/components/resources/StatTile'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchOverview, fetchWaste } from '@/lib/api'
import { formatCpu, formatMemory, formatPercent } from '@/lib/format'

export default function Overview() {
  const overview = useQuery({
    queryKey: ['namespace', 'overview'],
    queryFn: fetchOverview,
    refetchInterval: 15_000,
  })
  const waste = useQuery({
    queryKey: ['resources', 'waste', 5],
    queryFn: () => fetchWaste(5),
    refetchInterval: 15_000,
  })

  if (overview.isPending) return <Spinner label="Measuring the namespace…" />
  if (overview.error) return <ErrorPanel title="Could not read the namespace" error={overview.error} />

  const data = overview.data
  const r = data.totals.resources
  const budget = data.budget

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="CPU in use"
          value={formatCpu(r.usage.cpu_cores)}
          unit="cores"
          sub={`of ${formatCpu(r.requests.cpu_cores)} reserved`}
          footer={`${formatPercent(data.totals.cpu_efficiency)} of the reservation used`}
        >
          <CapacityBar
            label="Namespace CPU"
            used={r.usage.cpu_cores}
            reserved={r.requests.cpu_cores}
            limit={r.limits.cpu_cores}
            budget={budget.cpu_cores}
            format={formatCpu}
          />
        </StatTile>

        <StatTile
          label="Memory in use"
          value={formatMemory(r.usage.memory_bytes)}
          sub={`of ${formatMemory(r.requests.memory_bytes)} reserved`}
          footer={`${formatPercent(data.totals.memory_efficiency)} of the reservation used`}
        >
          <CapacityBar
            label="Namespace memory"
            used={r.usage.memory_bytes}
            reserved={r.requests.memory_bytes}
            limit={r.limits.memory_bytes}
            budget={budget.memory_bytes}
            format={formatMemory}
          />
        </StatTile>

        <StatTile
          label="Reserved vs budget"
          value={formatPercent(data.cpu_budget_used)}
          sub="of the CPU budget reserved"
          footer={
            <span title={budgetHint(budget.is_policy)}>
              budget: {budget.label}
            </span>
          }
        >
          <div className="space-y-2">
            <DualBar
              label="CPU"
              value={r.requests.cpu_cores}
              total={budget.cpu_cores}
              format={formatCpu}
            />
            <DualBar
              label="Memory"
              value={r.requests.memory_bytes}
              total={budget.memory_bytes}
              format={formatMemory}
            />
          </div>
        </StatTile>

        <StatTile
          label="Reclaimable"
          value={formatCpu(data.totals.reclaimable_cpu_cores)}
          unit="cores"
          sub={`${formatMemory(data.totals.reclaimable_memory_bytes)} of memory`}
          tone="attention"
          footer={
            <Link to="/capacity" className="inline-flex items-center gap-1 hover:text-arango">
              reserved but unused
              <ArrowRight size={11} aria-hidden />
            </Link>
          }
        >
          {data.reclaimable_cost_per_day !== null && (
            <p className="font-mono text-xs text-pit">
              ≈ ${data.reclaimable_cost_per_day.toFixed(2)}/day
            </p>
          )}
        </StatTile>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Chip label="Services" value={data.service_count}>
          {data.services_not_ready > 0 && (
            <span className="text-pit">{data.services_not_ready} not ready</span>
          )}
        </Chip>
        <Chip label="Workloads" value={data.workload_count}>
          {data.deployment_count} Deploy · {data.statefulset_count} STS
        </Chip>
        <Chip label="Pods" value={data.pod_count}>
          {data.ready_pods} ready
          {data.pods_with_recent_restarts > 0 && ` · ${data.pods_with_recent_restarts} restarted`}
        </Chip>
        <Chip label="No limits set" value={data.pods_without_limits_actionable} attention>
          {/* Counting the operator-managed database here would overstate the
              risk: omitting limits there is deliberate, and unfixable from this
              tool anyway. */}
          {data.pods_without_limits - data.pods_without_limits_actionable} more are the database
        </Chip>
      </div>

      {data.warning_services.length > 0 && (
        <section className="rounded-lg border border-pit-light bg-pit-light/30 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-pit">
            <AlertTriangle size={14} aria-hidden />
            Needs attention
          </h2>
          <ul className="mt-2 space-y-1">
            {data.warning_services.map((name) => (
              <li key={name}>
                <Link
                  to={`/services/${encodeURIComponent(name)}`}
                  className="font-mono text-xs text-body hover:text-arango hover:underline"
                >
                  {name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <header className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-body">Most reclaimable</h2>
          <Link to="/capacity" className="text-xs text-muted hover:text-arango">
            See all →
          </Link>
        </header>
        {waste.data && waste.data.length > 0 ? (
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-cream">
            {waste.data.map((item) => {
              // The row names a workload; the page that can act on it is its
              // service. Anything the grouping could not claim has no service
              // to open, so it stays inert rather than offering a dead link.
              const row = (
                <>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-body">
                    {item.name}
                  </span>
                  <span className="text-[11px] text-muted">{item.replicas}×</span>
                  {item.cpu_efficiency !== null && (
                    <span className="text-[11px] text-muted">
                      {(item.cpu_efficiency * 100).toFixed(1)}% used
                    </span>
                  )}
                  <span className="font-mono text-xs text-pit">
                    {formatCpu(item.reclaimable_cpu_cores)} cores
                  </span>
                </>
              )

              return (
                <li key={`${item.kind}/${item.name}`} className="text-sm">
                  {item.service ? (
                    <Link
                      to={`/services/${encodeURIComponent(item.service)}`}
                      title={`Open ${item.service}`}
                      className="flex items-center gap-3 px-3 py-2 transition-colors hover:bg-flesh-pale/40"
                    >
                      {row}
                    </Link>
                  ) : (
                    <span className="flex items-center gap-3 px-3 py-2">{row}</span>
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="text-xs text-muted">Nothing is over-reserved.</p>
        )}
      </section>
    </div>
  )
}

function budgetHint(isPolicy: boolean): string {
  return isPolicy
    ? 'A number set here, not a limit the cluster enforces. This credential is namespace-scoped and cannot read node capacity.'
    : 'Enforced by a ResourceQuota on this namespace.'
}

function Chip({
  label,
  value,
  children,
  attention,
}: {
  label: string
  value: number
  children?: React.ReactNode
  attention?: boolean
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 ${
        attention && value > 0 ? 'border-pit-light bg-pit-light/30' : 'border-line bg-panel'
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg text-body">{value}</span>
        <span className="text-xs text-muted">{label}</span>
      </div>
      <p className="text-[11px] text-muted">{children}</p>
    </div>
  )
}

import { AlertTriangle, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import Badge from '@/components/ui/Badge'
import { formatCpu, formatMemory } from '@/lib/format'
import type { Service } from '@/lib/schemas'

function readyTone(service: Service) {
  if (service.ready === false) return 'bad' as const
  if (service.ready === null) return 'neutral' as const
  return 'good' as const
}

export default function ServiceCard({ service }: { service: Service }) {
  const reservedCpu = service.resources.requests.cpu_cores
  const usedCpu = service.resources.usage.cpu_cores

  return (
    <Link
      to={`/services/${encodeURIComponent(service.name)}`}
      className="block rounded-lg border border-line bg-panel p-4 transition-colors hover:border-flesh-light hover:bg-flesh-pale/40"
    >
      <div className="flex items-start gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-semibold break-words text-body">
          {service.title}
        </h3>
        <Badge tone={readyTone(service)}>
          {service.ready === null ? 'unknown' : service.ready ? 'ready' : 'not ready'}
        </Badge>
      </div>

      {service.attribution && (
        <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-xs text-muted">
          {service.attribution.project && (
            <span className="font-medium text-body">{service.attribution.project}</span>
          )}
          {service.attribution.database && (
            <span className="font-mono">
              {service.attribution.project ? '· ' : ''}
              {service.attribution.database}
            </span>
          )}
          {service.attribution.conflict && (
            <span
              className="text-pit"
              title="Pods under this service report different values; the conflicting field is withheld."
            >
              · pods disagree
            </span>
          )}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {service.chart_version && (
          <Badge tone="neutral" mono title={`Chart ${service.chart_name ?? ''}`}>
            {service.chart_version}
          </Badge>
        )}
        {service.version_drift && (
          <Badge tone="warn" title={`Catalog offers ${service.catalog_version}`}>
            drift
          </Badge>
        )}
        <ProtectedBadge protection={service.protection} />
        {service.route_path && (
          <Badge tone="accent" mono title={`Served at ${service.route_path}`}>
            <ExternalLink size={10} aria-hidden />
            {service.route_path}
          </Badge>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-muted">Pods</dt>
          <dd className="font-mono text-body">
            {service.ready_pods}/{service.pod_count}
          </dd>
        </div>
        <div>
          <dt className="text-muted">CPU</dt>
          <dd className="font-mono text-body">
            {formatCpu(usedCpu)}
            <span className="text-muted"> / {formatCpu(reservedCpu)}</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted">Memory</dt>
          <dd className="font-mono text-body">
            {formatMemory(service.resources.usage.memory_bytes)}
            <span className="text-muted">
              {' '}
              / {formatMemory(service.resources.requests.memory_bytes)}
            </span>
          </dd>
        </div>
      </dl>

      {service.latest_warning && (
        <p className="mt-3 flex items-start gap-1.5 rounded-md bg-pit-light/40 p-2 text-[11px] text-pit">
          <AlertTriangle size={12} className="mt-px shrink-0" aria-hidden />
          <span className="line-clamp-2 break-words">{service.latest_warning}</span>
        </p>
      )}
    </Link>
  )
}

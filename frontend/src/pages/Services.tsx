import { useQuery } from '@tanstack/react-query'

import ServiceCard from '@/components/services/ServiceCard'
import EmptyState from '@/components/ui/EmptyState'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchServices } from '@/lib/api'
import type { Service } from '@/lib/schemas'

export default function Services() {
  const { data, error, isPending } = useQuery({
    queryKey: ['services'],
    queryFn: fetchServices,
    refetchInterval: 10_000,
  })

  if (isPending) return <Spinner label="Reading the namespace…" />
  if (error) return <ErrorPanel title="Could not list services" error={error} />

  // Platform services come from an ArangoPlatformService; the rest are things
  // running in the namespace that no platform service claims. Keeping them
  // apart makes the distinction visible instead of hiding it.
  const platform = data.filter((s) => s.source !== 'unmanaged')
  const unmanaged = data.filter((s) => s.source === 'unmanaged')
  const unhealthy = platform.filter((s) => s.ready === false).length

  return (
    <div className="space-y-8">
      <section>
        <header className="mb-3 flex items-baseline gap-3">
          <h2 className="text-sm font-semibold text-body">Platform services</h2>
          <p className="text-xs text-muted">
            {platform.length} deployed
            {unhealthy > 0 && <span className="text-pit"> · {unhealthy} not ready</span>}
          </p>
        </header>
        <Grid services={platform} />
      </section>

      {unmanaged.length > 0 && (
        <section>
          <header className="mb-3 flex items-baseline gap-3">
            <h2 className="text-sm font-semibold text-body">Not managed by a platform service</h2>
            <p className="text-xs text-muted">
              Running here, but no ArangoPlatformService claims them
            </p>
          </header>
          <Grid services={unmanaged} />
        </section>
      )}
    </div>
  )
}

function Grid({ services }: { services: Service[] }) {
  if (services.length === 0) {
    return <EmptyState title="Nothing here." />
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {services.map((service) => (
        <ServiceCard key={service.name} service={service} />
      ))}
    </div>
  )
}

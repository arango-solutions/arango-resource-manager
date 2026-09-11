import type { ClusterInfo } from '@/lib/schemas'

interface Props {
  info?: ClusterInfo
  error?: Error | null
}

/**
 * Phase 0 placeholder: proves the connection end to end. The stat tiles and
 * waste leaderboard land in Phase 2, once the rollup exists.
 */
export default function Overview({ info, error }: Props) {
  if (error) {
    return (
      <section className="rounded-lg border border-pit-light bg-pit-light/40 p-6">
        <h2 className="text-sm font-semibold text-pit">Cannot reach the namespace</h2>
        <p className="mt-1 font-mono text-xs text-body">{error.message}</p>
        <p className="mt-3 text-xs text-muted">
          Check <code className="font-mono">ARM_KUBE_CONTEXT</code> and{' '}
          <code className="font-mono">ARM_NAMESPACE</code> in{' '}
          <code className="font-mono">backend/.env</code>, then restart the API.
        </p>
      </section>
    )
  }

  if (!info) {
    return <p className="text-sm text-muted">Connecting to the namespace…</p>
  }

  const caps = info.capabilities
  const crs = Array.isArray(caps.arango_crs) ? (caps.arango_crs as string[]) : []

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-line bg-panel p-6">
        <h2 className="text-sm font-semibold text-body">Connected</h2>
        <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 text-sm md:grid-cols-5">
          {/* The namespace is the thing the user most needs to read, so it gets
              the room. Truncating it would hide the part that differs. */}
          <Field label="Namespace" value={info.namespace} mono className="md:col-span-2" />
          <Field label="Context" value={info.context} mono />
          <Field label="Kubernetes" value={info.server_version ?? 'unknown'} mono />
          <Field label="Config source" value={info.config_source} mono />
        </dl>
      </section>

      <section className="rounded-lg border border-line bg-panel p-6">
        <h2 className="text-sm font-semibold text-body">Arango custom resources</h2>
        <p className="mt-1 text-xs text-muted">
          The platform objects this namespace exposes. Services are grouped from these in Phase 1.
        </p>
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {crs.map((kind) => (
            <li
              key={kind}
              className="rounded-full border border-flesh-light bg-flesh-pale px-2 py-0.5 font-mono text-[11px] text-arango"
            >
              {kind}
            </li>
          ))}
        </ul>
      </section>

      {info.safety.read_only && (
        <section className="rounded-lg border border-pit-light bg-pit-light/40 p-4">
          <h2 className="text-sm font-semibold text-pit">Read-only</h2>
          <p className="mt-1 text-xs text-body">
            Every mutating route returns 403 while{' '}
            <code className="font-mono">ARM_READ_ONLY</code> is set. Actions arrive in Phase 4.
          </p>
        </section>
      )}
    </div>
  )
}

function Field({
  label,
  value,
  mono,
  className = '',
}: {
  label: string
  value: string
  mono?: boolean
  className?: string
}) {
  return (
    <div className={`min-w-0 ${className}`}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`break-all text-body ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  )
}

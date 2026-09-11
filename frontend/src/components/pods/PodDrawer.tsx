import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import { useState } from 'react'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import Badge from '@/components/ui/Badge'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchPod, fetchPodLogs } from '@/lib/api'
import { formatCpu, formatMemory } from '@/lib/format'
import { formatUptime } from '@/lib/uptime'
import type { PodDetail } from '@/lib/schemas'

interface Props {
  name: string
  onClose: () => void
}

export default function PodDrawer({ name, onClose }: Props) {
  const { data, error, isPending } = useQuery({
    queryKey: ['pods', name],
    queryFn: () => fetchPod(name),
    refetchInterval: 10_000,
  })

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="flex-1 bg-skin/25"
      />
      <aside className="flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-line bg-cream shadow-xl">
        <header className="sticky top-0 flex items-start gap-3 border-b border-line bg-cream px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 className="font-mono text-sm break-all text-body">{name}</h2>
            {data && (
              <p className="mt-0.5 text-xs text-muted">
                {data.service ?? 'no service'} · {data.node ?? 'unscheduled'}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted hover:bg-panel hover:text-body"
            aria-label="Close pod details"
          >
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 space-y-5 px-5 py-4">
          {isPending && <Spinner label="Reading pod…" />}
          {error && <ErrorPanel title="Could not read this pod" error={error} />}
          {data && <Body pod={data} />}
        </div>
      </aside>
    </div>
  )
}

function Body({ pod }: { pod: PodDetail }) {
  const [container, setContainer] = useState(pod.containers[0] ?? '')
  const [previous, setPrevious] = useState(false)

  const logs = useQuery({
    queryKey: ['pods', pod.name, 'logs', container, previous],
    queryFn: () => fetchPodLogs(pod.name, { container, previous, tailLines: 200 }),
    enabled: Boolean(container),
    retry: false,
  })

  const hasRestarts = pod.restart_count > 0

  return (
    <>
      <section className="flex flex-wrap items-center gap-2">
        <Badge tone={pod.ready ? 'good' : 'warn'}>{pod.phase}</Badge>
        <Badge tone="neutral" mono>
          {pod.ready_containers} ready
        </Badge>
        <ProtectedBadge protection={pod.protection} />
      </section>

      {pod.protection.reason && (
        <p className="rounded-md border border-line bg-panel p-3 text-xs text-body">
          {pod.protection.reason}{' '}
          <span className="text-muted">{pod.protection.remediation}</span>
        </p>
      )}

      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Containers</h3>
        <div className="space-y-2">
          {pod.container_details.map((c) => (
            <div key={c.name} className="rounded-md border border-line bg-panel p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-body">{c.name}</span>
                <Badge tone={c.ready ? 'good' : 'warn'}>{c.state ?? 'unknown'}</Badge>
                {c.restart_count > 0 && (
                  <Badge tone="warn" title={c.last_terminated_reason ?? undefined}>
                    {c.restart_count} restart{c.restart_count > 1 ? 's' : ''}
                    {c.last_terminated_reason && ` · ${c.last_terminated_reason}`}
                  </Badge>
                )}
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] sm:grid-cols-3">
                <Pair
                  label="running for"
                  value={c.started_at ? sinceLabel(c.started_at) : '—'}
                  hint={c.started_at ?? undefined}
                />
                <Pair
                  label="cpu"
                  value={`${formatCpu(c.resources.requests.cpu_cores)} / ${formatCpu(
                    c.resources.limits.cpu_cores,
                  )}`}
                  hint="request / limit"
                />
                <Pair
                  label="memory"
                  value={`${formatMemory(c.resources.requests.memory_bytes)} / ${formatMemory(
                    c.resources.limits.memory_bytes,
                  )}`}
                  hint="request / limit"
                />
              </dl>
            </div>
          ))}
        </div>
        {hasRestarts && (
          <p className="mt-2 flex items-start gap-1.5 text-[11px] text-muted">
            <AlertTriangle size={11} className="mt-px shrink-0 text-pit" aria-hidden />
            {/* The distinction that hides the problem if you miss it. */}
            The pod has been up {formatUptime(pod.age_seconds)}, but a container restarted inside
            it — so the container is younger than the pod. The previous log below is where the
            reason is written down.
          </p>
        )}
      </section>

      <section>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Logs</h3>
          {pod.containers.length > 1 && (
            <select
              value={container}
              onChange={(event) => setContainer(event.target.value)}
              className="rounded border border-line bg-cream px-1.5 py-0.5 font-mono text-[11px] text-body"
            >
              {pod.containers.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          <label className="flex items-center gap-1 text-[11px] text-muted">
            <input
              type="checkbox"
              checked={previous}
              onChange={(event) => setPrevious(event.target.checked)}
              className="accent-arango"
            />
            previous instance
          </label>
        </div>

        {logs.isFetching && <Spinner label="Reading logs…" />}
        {logs.error && (
          <p className="rounded-md border border-pit-light bg-pit-light/30 p-3 text-xs text-body">
            {logErrorMessage(logs.error)}
          </p>
        )}
        {logs.data && !logs.isFetching && (
          <pre className="max-h-96 overflow-auto rounded-md border border-line bg-panel p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-body">
            {logs.data}
          </pre>
        )}
      </section>
    </>
  )
}

function Pair({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <dt className="text-muted">{label}</dt>
      <dd className="text-body">{value}</dd>
    </div>
  )
}

function sinceLabel(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000))
  return formatUptime(seconds)
}

function logErrorMessage(error: unknown): string {
  // The log route is fetched as raw text, so an error body arrives as an
  // unparsed JSON string rather than an object - parse it to surface the
  // backend's explanation ("pick a container", "no previous log") instead of
  // a bare "Request failed with status code 400".
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data) as { detail?: string }
      if (parsed.detail) return parsed.detail
    } catch {
      if (data.trim()) return data
    }
  } else if (data && typeof data === 'object' && 'detail' in data) {
    return String((data as { detail: unknown }).detail)
  }
  return error instanceof Error ? error.message : 'Could not read the log.'
}

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useState } from 'react'

import ActionDialog from '@/components/actions/ActionDialog'
import ConditionList from '@/components/services/ConditionList'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchDatabase, scaleDatabase } from '@/lib/api'
import type { Tier } from '@/lib/schemas'

/**
 * The correct way to resize the cluster. Everywhere else in this app, an
 * ArangoDB member is protected and its buttons are absent — because scaling it
 * through the core Kubernetes API is reconciled straight back by the operator.
 * Here the ArangoDeployment spec is edited instead, which is what the operator
 * actually reads.
 */
export default function Database() {
  const { data, error, isPending } = useQuery({
    queryKey: ['database'],
    queryFn: fetchDatabase,
    refetchInterval: 10_000,
  })

  if (isPending) return <Spinner label="Reading the database…" />
  if (error) return <ErrorPanel title="Could not read the ArangoDeployment" error={error} />

  return (
    <div className="max-w-4xl space-y-5">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-body">{data.name}</h2>
        <Badge tone="neutral" mono>
          {data.mode ?? 'unknown'}
        </Badge>
        <Badge tone={data.ready ? 'good' : 'warn'}>{data.ready ? 'ready' : 'not ready'}</Badge>
      </header>

      {!data.scaling_enabled && (
        <p className="rounded-md border border-line bg-panel p-3 text-xs text-body">
          Resizing is disabled. Set{' '}
          <code className="font-mono text-[11px]">ARM_ALLOW_DATABASE_SCALING=true</code> where the
          API is started to enable it. Agents stay fixed regardless — see below.
        </p>
      )}

      <section className="space-y-3">
        {data.tiers.map((tier) => (
          <TierRow key={tier.name} tier={tier} />
        ))}
      </section>

      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-body">Operator status</h3>
        <ConditionList conditions={data.conditions} />
      </Card>
    </div>
  )
}

function TierRow({ tier }: { tier: Tier }) {
  const [target, setTarget] = useState(tier.count)
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const immutable = tier.policy === 'immutable'
  const changed = target !== tier.count

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-mono text-sm text-body">{tier.name}</h3>
        <Badge tone="neutral" mono>
          {tier.ready}/{tier.count} ready
        </Badge>
        {immutable && (
          <Badge tone="neutral" title={tier.note}>
            <Lock size={11} aria-hidden />
            fixed
          </Badge>
        )}
        {tier.policy === 'drain-on-shrink' && (
          <Badge tone="warn" title={tier.note}>
            drains on shrink
          </Badge>
        )}

        {!immutable && (
          <div className="ml-auto flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={16}
              value={target}
              disabled={!tier.scalable}
              onChange={(event) => setTarget(Number(event.target.value))}
              className="w-16 rounded border border-line bg-cream px-2 py-1 font-mono text-xs text-body disabled:opacity-40"
            />
            <button
              type="button"
              disabled={!tier.scalable || !changed}
              onClick={() => setOpen(true)}
              className="rounded bg-arango px-2.5 py-1 text-[11px] font-medium text-white hover:bg-arango-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              Apply
            </button>
          </div>
        )}
      </div>

      <p className="mt-2 max-w-prose text-xs text-muted">{tier.note}</p>

      {open && (
        <ActionDialog
          title={`Scale ${tier.name} to ${target}`}
          confirmLabel={`Set ${tier.name} to ${target}`}
          destructive={target < tier.count}
          run={(dryRun) => scaleDatabase(tier.name, target, dryRun)}
          onDone={() => {
            setOpen(false)
            void queryClient.invalidateQueries()
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </Card>
  )
}

import { AlertTriangle, ShieldCheck } from 'lucide-react'

import { formatCpu, formatMemory } from '@/lib/format'
import type { ActionPlan } from '@/lib/schemas'
import { formatUptime } from '@/lib/uptime'

/**
 * What the action would do, computed by the server rather than guessed here.
 * The pods are listed with their uptime: a count says "20 pods", this says
 * which twenty and how long they have been up.
 */
export default function PlanDiff({ plan }: { plan: ActionPlan }) {
  const showsReplicas = plan.current_replicas !== null && plan.target_replicas !== null

  return (
    <div className="space-y-3">
      {showsReplicas && (
        <p className="font-mono text-sm text-body">
          {plan.current_replicas} → <span className="font-semibold">{plan.target_replicas}</span>{' '}
          replicas
        </p>
      )}

      {plan.warning && (
        <p className="flex items-start gap-2 rounded-md bg-pit-light/50 p-3 text-xs text-body">
          <AlertTriangle size={13} className="mt-px shrink-0 text-pit" aria-hidden />
          {plan.warning}
        </p>
      )}

      {plan.targets.length > 1 && (
        <p className="text-xs text-muted">
          {plan.targets.length} workloads:{' '}
          <span className="font-mono text-body">
            {plan.targets.map((target) => target.name).join(', ')}
          </span>
        </p>
      )}

      {plan.pods_terminating.length > 0 && (
        <div>
          <p className="mb-1 text-xs text-muted">
            {plan.pods_terminating.length} pod
            {plan.pods_terminating.length > 1 ? 's' : ''} would be terminated
          </p>
          <ul className="max-h-40 overflow-y-auto rounded-md border border-line bg-panel">
            {plan.pods_terminating.map((pod) => (
              <li
                key={pod.name}
                className="flex items-center gap-2 px-2 py-1 font-mono text-[11px]"
              >
                <span className="min-w-0 flex-1 truncate text-body">{pod.name}</span>
                <span className="text-muted">up {formatUptime(pod.age_seconds)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(plan.frees.cpu_cores !== null || plan.frees.memory_bytes !== null) && (
        <p className="font-mono text-xs text-arango">
          frees {formatCpu(plan.frees.cpu_cores)} cores ·{' '}
          {formatMemory(plan.frees.memory_bytes)} of reservation
        </p>
      )}

      {plan.restore_to !== null && (
        <p className="text-xs text-muted">
          Restoring later will set it back to{' '}
          <span className="font-mono text-body">{plan.restore_to}</span>.
        </p>
      )}

      {plan.server_dry_run === 'accepted' && (
        <p className="flex items-center gap-1.5 text-[11px] text-arango">
          <ShieldCheck size={12} aria-hidden />
          {/* Not a client-side guess: the API server authorised this exact
              change without persisting it. */}
          validated by the API server
        </p>
      )}
    </div>
  )
}

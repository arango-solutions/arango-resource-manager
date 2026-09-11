import { useEffect, useState } from 'react'

import PlanDiff from '@/components/actions/PlanDiff'
import Spinner from '@/components/ui/Spinner'
import type { ActionPlan, ActionResult } from '@/lib/schemas'

interface Props {
  title: string
  confirmLabel: string
  destructive?: boolean
  /** Runs the action. Called first with dryRun true, then for real on confirm. */
  run: (dryRun: boolean) => Promise<ActionResult>
  onDone: () => void
  onClose: () => void
  children?: React.ReactNode
}

/**
 * The confirmation ladder.
 *
 * The dialog opens by running the action as a server-side dry run, so the user
 * is never asked to approve something whose consequences have not been
 * computed — and an RBAC gap or webhook rejection surfaces before they type
 * anything, not after.
 *
 * When the plan says so, confirming also requires typing the workload's name.
 * That gate is reserved for actions that stop a service serving requests.
 */
export default function ActionDialog({
  title,
  confirmLabel,
  destructive,
  run,
  onDone,
  onClose,
  children,
}: Props) {
  const [plan, setPlan] = useState<ActionPlan | null>(null)
  const [blocked, setBlocked] = useState<ActionResult | null>(null)
  const [typed, setTyped] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    run(true)
      .then((result) => {
        if (cancelled) return
        if (result.blocked_reason) setBlocked(result)
        else setPlan(result.plan)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => !cancelled && setBusy(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const needsTyping = plan?.requires_typed_confirmation ?? false
  const ready =
    plan !== null && (!needsTyping || (typed === plan.name && acknowledged)) && !busy

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      const result = await run(false)
      if (result.blocked_reason) setBlocked(result)
      else onDone()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" aria-label="Cancel" onClick={onClose} className="absolute inset-0 bg-skin/40" />
      <div className="relative z-10 w-full max-w-lg space-y-4 rounded-lg border border-line bg-cream p-5 shadow-xl">
        <h2 className="text-sm font-semibold text-body">{title}</h2>

        {busy && !plan && !blocked && <Spinner label="Checking what this would do…" />}

        {blocked && (
          <div className="space-y-2 rounded-md border border-pit-light bg-pit-light/40 p-3">
            <p className="text-xs font-medium text-pit">{blocked.detail}</p>
            {blocked.remediation && <p className="text-xs text-body">{blocked.remediation}</p>}
          </div>
        )}

        {plan && !blocked && (
          <>
            {children}
            <PlanDiff plan={plan} />

            {needsTyping && (
              <div className="space-y-2 rounded-md border border-line bg-panel p-3">
                <label className="block text-xs text-body">
                  Type <span className="font-mono font-semibold">{plan.name}</span> to confirm
                  <input
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    className="mt-1 w-full rounded border border-line bg-cream px-2 py-1 font-mono text-xs text-body"
                  />
                </label>
                <label className="flex items-start gap-2 text-xs text-body">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                    className="mt-0.5 accent-arango"
                  />
                  I understand requests to this service will fail until it is restored.
                </label>
              </div>
            )}
          </>
        )}

        {error && <p className="font-mono text-xs text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line px-3 py-1.5 text-xs text-body hover:bg-panel"
          >
            Cancel
          </button>
          {!blocked && (
            <button
              type="button"
              disabled={!ready}
              onClick={confirm}
              className={`rounded px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40 ${
                destructive ? 'bg-danger hover:brightness-90' : 'bg-arango hover:bg-arango-hover'
              }`}
            >
              {busy ? 'Working…' : confirmLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

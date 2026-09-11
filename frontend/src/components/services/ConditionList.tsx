import { Check, X } from 'lucide-react'

import type { Condition } from '@/lib/schemas'

/**
 * Conditions say WHICH check failed. They rarely say why - the platform
 * reports `ReleaseReady: False / "Not ready"` - so the diagnosis comes from the
 * event feed alongside this.
 */
export default function ConditionList({ conditions }: { conditions: Condition[] }) {
  if (conditions.length === 0) {
    return <p className="text-xs text-muted">This service reports no status conditions.</p>
  }

  return (
    <ul className="space-y-1.5">
      {conditions.map((condition) => (
        <li key={condition.type} className="flex items-start gap-2 text-xs">
          {condition.status ? (
            <Check size={13} className="mt-px shrink-0 text-arango" aria-label="passing" />
          ) : (
            <X size={13} className="mt-px shrink-0 text-pit" aria-label="failing" />
          )}
          <span className={condition.status ? 'text-muted' : 'font-medium text-body'}>
            {condition.type}
          </span>
          {condition.message && condition.message !== condition.type && (
            <span className="text-muted">— {condition.message}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

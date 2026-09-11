import { Lock, ShieldAlert } from 'lucide-react'

import Badge from '@/components/ui/Badge'
import type { Protection } from '@/lib/schemas'

/**
 * Marks a workload this tool will not act on through the core Kubernetes API.
 * The tooltip carries the remediation, so the badge explains rather than just
 * refuses.
 */
export default function ProtectedBadge({ protection }: { protection: Protection }) {
  if (protection.level === 'normal') return null

  const isProtected = protection.level === 'protected'
  const tooltip = [protection.reason, protection.remediation].filter(Boolean).join(' ')

  return (
    <Badge tone={isProtected ? 'neutral' : 'warn'} title={tooltip}>
      {isProtected ? <Lock size={11} aria-hidden /> : <ShieldAlert size={11} aria-hidden />}
      {isProtected ? 'Protected' : 'Guarded'}
    </Badge>
  )
}

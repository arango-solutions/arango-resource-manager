import { RotateCcw } from 'lucide-react'

import Badge from '@/components/ui/Badge'
import { isRecent } from '@/lib/uptime'

interface Props {
  count: number
  lastRestartAt: string | null
}

export default function RestartBadge({ count, lastRestartAt }: Props) {
  if (count === 0) return <span className="text-xs text-muted">—</span>

  const recent = isRecent(lastRestartAt)
  return (
    <Badge
      tone={recent ? 'warn' : 'neutral'}
      title={
        lastRestartAt
          ? `Last restart ${lastRestartAt}${recent ? ' — within the last hour' : ''}`
          : undefined
      }
    >
      <RotateCcw size={11} aria-hidden />
      {count}
    </Badge>
  )
}

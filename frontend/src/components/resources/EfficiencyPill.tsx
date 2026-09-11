import Badge from '@/components/ui/Badge'
import { formatPercent } from '@/lib/format'

/**
 * Green at or above 60%, muted in the middle, pit brown below 20%. Brown, not
 * red: low efficiency wants attention, it is not a destructive act.
 */
export default function EfficiencyPill({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <span className="text-xs text-muted" title="Usage is unknown, so efficiency cannot be computed">
        —
      </span>
    )
  }
  const tone = value >= 0.6 ? 'good' : value >= 0.2 ? 'neutral' : 'warn'
  return (
    <Badge tone={tone} mono title={`Using ${formatPercent(value)} of what it reserved`}>
      {formatPercent(value)}
    </Badge>
  )
}

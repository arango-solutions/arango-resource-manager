interface Props {
  used: number | null
  reserved: number | null
  limit: number | null
  budget: number | null
  format: (value: number | null) => string
  label: string
}

/**
 * One bar, reused at every scope: namespace, service, workload, pod.
 *
 * It reads as a cross-section of the avocado, darkest at the core — solid
 * Arango green for what is actually used, pale flesh for what is reserved
 * around it, and a tick where the burst limit sits. The whole point is that
 * the gap between the green and the pale is the waste.
 *
 * Never colour-only: the same numbers appear in the caption beneath and in the
 * aria-label.
 */
export default function CapacityBar({ used, reserved, limit, budget, format, label }: Props) {
  // The track is whatever is largest, so nothing is ever drawn off the end.
  const track = Math.max(budget ?? 0, reserved ?? 0, limit ?? 0, used ?? 0) || 1
  const pct = (value: number | null) => (value === null ? 0 : Math.min(100, (value / track) * 100))

  const overBudget = budget !== null && limit !== null && limit > budget

  const caption = [
    `${format(used)} used`,
    `${format(reserved)} reserved`,
    `${format(limit)} limit`,
    budget !== null ? `${format(budget)} budget` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div>
      <div
        role="img"
        aria-label={`${label}: ${caption}`}
        className="relative h-2.5 w-full overflow-hidden rounded-full border border-line bg-panel"
      >
        <div
          className="absolute inset-y-0 left-0 bg-flesh-light"
          style={{ width: `${pct(reserved)}%` }}
        />
        <div className="absolute inset-y-0 left-0 bg-arango" style={{ width: `${pct(used)}%` }} />
        {limit !== null && (
          <div
            className="absolute inset-y-0 w-0.5 bg-flesh-deep"
            style={{ left: `calc(${pct(limit)}% - 1px)` }}
            title={`limit ${format(limit)}`}
          />
        )}
      </div>

      <p className="mt-1 font-mono text-[11px] text-muted">{caption}</p>
      {overBudget && (
        // Its own line: wrapped mid-caption on a narrow tile it read as part of
        // the numbers rather than as a remark about them.
        <p className="font-mono text-[11px] text-pit" title="Limits exceed the budget">
          ▸ limits exceed the budget
        </p>
      )}
    </div>
  )
}

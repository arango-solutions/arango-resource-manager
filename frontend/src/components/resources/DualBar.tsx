interface Props {
  label: string
  value: number | null
  total: number | null
  format: (value: number | null) => string
}

/** Reserved against budget. Used on the overview tile that pairs CPU and memory. */
export default function DualBar({ label, value, total, format }: Props) {
  const ratio = value !== null && total ? Math.min(1, value / total) : 0
  const pct = Math.round(ratio * 100)

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between font-mono text-[11px]">
        <span className="text-muted">{label}</span>
        <span className="text-body">
          {format(value)} / {format(total)}
          <span className="ml-1 text-muted">{total ? `${pct}%` : ''}</span>
        </span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${format(value)} of ${format(total)}`}
        className="h-1.5 w-full overflow-hidden rounded-full border border-line bg-panel"
      >
        <div className="h-full bg-arango" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

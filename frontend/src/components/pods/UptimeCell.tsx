import { formatUptime, isYoung } from '@/lib/uptime'

interface Props {
  seconds: number | null
  startedAt: string | null
}

export default function UptimeCell({ seconds, startedAt }: Props) {
  const young = isYoung(seconds)
  return (
    <span
      title={startedAt ?? undefined}
      className={`font-mono text-xs ${young ? 'font-semibold text-body' : 'text-muted'}`}
    >
      {formatUptime(seconds)}
    </span>
  )
}

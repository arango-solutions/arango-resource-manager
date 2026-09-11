import Badge, { type Tone } from '@/components/ui/Badge'

const PHASE_TONE: Record<string, Tone> = {
  Running: 'good',
  Succeeded: 'neutral',
  Pending: 'warn',
  Failed: 'bad',
  Unknown: 'warn',
}

interface Props {
  phase: string
  ready: boolean
  readyContainers: string
}

export default function PodStatusPill({ phase, ready, readyContainers }: Props) {
  // Running but not all containers ready is its own state, and the one most
  // worth noticing: the pod looks fine in `kubectl get pods` at a glance.
  const tone: Tone = phase === 'Running' && !ready ? 'warn' : (PHASE_TONE[phase] ?? 'neutral')
  return (
    <Badge tone={tone} title={`${phase} — ${readyContainers} containers ready`}>
      {phase === 'Running' ? readyContainers : phase}
    </Badge>
  )
}

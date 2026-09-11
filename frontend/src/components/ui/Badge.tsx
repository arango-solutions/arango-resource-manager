import type { ReactNode } from 'react'

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'accent'

const TONES: Record<Tone, string> = {
  neutral: 'border-line bg-cream text-muted',
  good: 'border-flesh-light bg-flesh-pale text-arango',
  warn: 'border-pit-light bg-pit-light/50 text-pit',
  bad: 'border-danger/30 bg-danger/5 text-danger',
  accent: 'border-flesh-light bg-flesh-pale text-flesh-deep',
}

interface Props {
  tone?: Tone
  title?: string
  mono?: boolean
  children: ReactNode
}

export default function Badge({ tone = 'neutral', title, mono, children }: Props) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] leading-4 ${
        TONES[tone]
      } ${mono ? 'font-mono' : ''}`}
    >
      {children}
    </span>
  )
}

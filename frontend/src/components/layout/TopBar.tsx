import type { Chip } from '@/lib/capability'

interface Props {
  namespace?: string
  context?: string
  chips: Chip[]
}

const TONE_CLASS: Record<Chip['tone'], string> = {
  ok: 'bg-flesh-pale text-arango border-flesh-light',
  off: 'bg-panel text-muted border-line',
  warn: 'bg-pit-light text-pit border-pit-light',
}

export default function TopBar({ namespace, context, chips }: Props) {
  return (
    <header className="flex items-center gap-4 border-b border-line bg-cream px-6 py-3">
      <div className="min-w-0">
        <h1 className="truncate font-mono text-sm font-semibold text-body">
          {namespace ?? 'connecting…'}
        </h1>
        {context && <p className="truncate text-xs text-muted">context {context}</p>}
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        {chips.map((chip) => (
          <span
            key={chip.label}
            title={chip.title}
            className={`rounded-full border px-2 py-0.5 text-[11px] ${TONE_CLASS[chip.tone]}`}
          >
            {chip.label}
          </span>
        ))}
      </div>
    </header>
  )
}

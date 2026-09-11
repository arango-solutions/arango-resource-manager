interface Props {
  title: string
  phase: string
  children: string
}

/** Stands in for a page that a later phase fills in. */
export default function Placeholder({ title, phase, children }: Props) {
  return (
    <section className="rounded-lg border border-line bg-panel p-6">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-body">{title}</h2>
        <span className="rounded-full border border-line bg-cream px-2 py-0.5 text-[11px] text-muted">
          {phase}
        </span>
      </div>
      <p className="mt-2 max-w-prose text-sm text-muted">{children}</p>
    </section>
  )
}

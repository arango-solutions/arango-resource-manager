interface Props {
  title: string
  hint?: string
}

export default function EmptyState({ title, hint }: Props) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-panel/60 px-6 py-10 text-center">
      <p className="text-sm text-body">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-prose text-xs text-muted">{hint}</p>}
    </div>
  )
}

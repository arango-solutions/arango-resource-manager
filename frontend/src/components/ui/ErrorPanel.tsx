interface Props {
  title: string
  error: unknown
}

export default function ErrorPanel({ title, error }: Props) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div className="rounded-lg border border-pit-light bg-pit-light/40 p-5">
      <h2 className="text-sm font-semibold text-pit">{title}</h2>
      <p className="mt-1 font-mono text-xs break-all text-body">{message}</p>
    </div>
  )
}

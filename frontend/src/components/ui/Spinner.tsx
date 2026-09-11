export default function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-arango" />
      {label}
    </p>
  )
}

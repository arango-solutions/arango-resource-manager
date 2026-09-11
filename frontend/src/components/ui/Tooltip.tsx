import { useId, useState } from 'react'

interface Props {
  /** The tooltip text. When empty, the child renders bare. */
  label?: string
  /** Sits above by default; below when the trigger is near the top of a panel. */
  side?: 'top' | 'bottom'
  children: React.ReactNode
}

/**
 * A hover/focus tooltip that also works over a *disabled* control.
 *
 * The native `title` attribute does not, which matters here more than it
 * sounds: the buttons carry their explanation precisely when they are
 * disabled — "this instance is read-only", "already at zero replicas" — and a
 * browser fires no pointer events on a disabled button, so that `title` never
 * appears. The one hint worth reading is the one you cannot see.
 *
 * Listening on a wrapping span instead solves it: the span is not disabled, so
 * it still receives hover, and focus events bubble from the control when the
 * control is focusable.
 */
export default function Tooltip({ label, side = 'top', children }: Props) {
  const [open, setOpen] = useState(false)
  const id = useId()

  if (!label) return <>{children}</>

  const position =
    side === 'top' ? 'bottom-full mb-1.5 origin-bottom' : 'top-full mt-1.5 origin-top'

  return (
    <span
      className="relative inline-flex"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined} className="inline-flex">
        {children}
      </span>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`pointer-events-none absolute left-1/2 z-50 w-max max-w-56 -translate-x-1/2 rounded-md border border-line bg-body px-2 py-1 text-[11px] leading-snug text-cream shadow-lg ${position}`}
        >
          {label}
        </span>
      )}
    </span>
  )
}

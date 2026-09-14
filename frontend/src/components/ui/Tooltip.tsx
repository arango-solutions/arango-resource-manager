import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  /** The tooltip text. When empty, the child renders bare. */
  label?: string
  /** Preferred side; flips automatically when there is no room. */
  side?: 'top' | 'bottom'
  children: React.ReactNode
}

/** Keep this far from the viewport edge, and this far from the trigger. */
const MARGIN = 8
const GAP = 6

/**
 * A hover/focus tooltip that also works over a *disabled* control.
 *
 * The native `title` attribute does not, which matters here more than it
 * sounds: the buttons carry their explanation precisely when they are
 * disabled — "read-only mode is on", "already at zero replicas" — and a
 * browser fires no pointer events on a disabled button, so that `title` never
 * appears. The one hint worth reading is the one you cannot see. Listening on
 * a wrapping span solves it: the span is not disabled, so it still gets hover.
 *
 * It renders through a portal with fixed positioning rather than absolutely
 * inside the trigger, for two reasons. These buttons sit at the right edge of
 * a card (`ml-auto`), so a centred tooltip runs off the page — the position is
 * measured and clamped to the viewport instead. And an absolutely positioned
 * tooltip is clipped by any `overflow: hidden` ancestor, which a rounded card
 * usually is.
 */
export default function Tooltip({ label, side = 'top', children }: Props) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tipRef = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const id = useId()

  const place = useCallback(() => {
    const trigger = triggerRef.current?.getBoundingClientRect()
    const tip = tipRef.current?.getBoundingClientRect()
    if (!trigger || !tip) return

    // Centre on the trigger, then pull back inside whichever edge it crosses.
    const centred = trigger.left + trigger.width / 2 - tip.width / 2
    const maxLeft = window.innerWidth - tip.width - MARGIN
    const left = Math.max(MARGIN, Math.min(centred, maxLeft))

    const above = trigger.top - tip.height - GAP
    const below = trigger.bottom + GAP
    const fitsAbove = above >= MARGIN
    const fitsBelow = below + tip.height <= window.innerHeight - MARGIN
    const top = side === 'top' ? (fitsAbove ? above : below) : fitsBelow ? below : above

    setPos({ left, top })
  }, [side])

  // Measured before paint, so it never appears in the wrong place first.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  if (!label) return <>{children}</>

  return (
    <>
      <span
        ref={triggerRef}
        className="relative inline-flex"
        onPointerEnter={() => setOpen(true)}
        onPointerLeave={() => setOpen(false)}
        onFocusCapture={() => setOpen(true)}
        onBlurCapture={() => setOpen(false)}
      >
        <span aria-describedby={open ? id : undefined} className="inline-flex">
          {children}
        </span>
      </span>

      {open &&
        createPortal(
          <span
            ref={tipRef}
            id={id}
            role="tooltip"
            style={{
              left: pos?.left ?? 0,
              top: pos?.top ?? 0,
              // Hidden for the first frame, while the size is still unknown.
              visibility: pos ? 'visible' : 'hidden',
            }}
            className="pointer-events-none fixed z-50 w-max max-w-64 rounded-md border border-line bg-body px-2 py-1 text-[11px] leading-snug text-cream shadow-lg"
          >
            {label}
          </span>,
          document.body
        )}
    </>
  )
}

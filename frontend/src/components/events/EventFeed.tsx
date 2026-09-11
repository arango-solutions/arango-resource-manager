import { AlertTriangle } from 'lucide-react'

import type { EventItem } from '@/lib/schemas'

export default function EventFeed({ events }: { events: EventItem[] }) {
  if (events.length === 0) {
    return <p className="text-xs text-muted">No warnings recorded for this service.</p>
  }

  return (
    <ul className="space-y-2">
      {events.map((event, index) => (
        <li
          key={`${event.involved_name}-${event.reason}-${index}`}
          className="rounded-md border border-pit-light bg-pit-light/30 p-3"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle size={12} className="shrink-0 text-pit" aria-hidden />
            <span className="text-xs font-medium text-pit">{event.reason ?? 'Warning'}</span>
            {event.count > 1 && <span className="text-[11px] text-muted">×{event.count}</span>}
            <span className="ml-auto font-mono text-[11px] text-muted">
              {event.involved_name}
            </span>
          </div>
          {event.message && (
            <p className="mt-1.5 font-mono text-[11px] leading-relaxed break-words text-body">
              {event.message}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

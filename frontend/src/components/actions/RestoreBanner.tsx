import { useQueryClient } from '@tanstack/react-query'
import { Undo2 } from 'lucide-react'
import { useState } from 'react'

import ActionDialog from '@/components/actions/ActionDialog'
import Tooltip from '@/components/ui/Tooltip'
import { restoreWorkload } from '@/lib/api'
import type { Stopped } from '@/lib/schemas'

interface Props {
  kind: string
  name: string
  record?: Stopped[string]
  readOnly: boolean
}

/**
 * Shown on anything sitting at zero replicas. If this tool stopped it, the
 * previous count is known and offered. If it did not, it says so rather than
 * inventing a number.
 */
export default function RestoreBanner({ kind, name, record, readOnly }: Props) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-pit-light bg-pit-light/40 px-3 py-2">
      <span className="text-xs text-body">
        {record ? (
          <>
            Stopped by this tool · was{' '}
            <span className="font-mono font-semibold">{record.previous_replicas}</span> replicas
          </>
        ) : (
          <>Stopped, but not by this tool — the previous replica count is unknown.</>
        )}
      </span>
      <Tooltip
        label={
          readOnly
            ? 'Read-only mode is on (ARM_READ_ONLY). No action will run.'
            : record
              ? `Scale back to ${record.previous_replicas}, the count recorded when it was stopped`
              : 'Scale back to 1 — the previous count was not recorded, so it is a guess'
        }
      >
        <button
          type="button"
          disabled={readOnly}
          onClick={() => setOpen(true)}
          className="ml-auto inline-flex items-center gap-1 rounded bg-arango px-2 py-1 text-[11px] font-medium text-white hover:bg-arango-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Undo2 size={11} aria-hidden />
          Restore to {record?.previous_replicas ?? 1}
        </button>
      </Tooltip>

      {open && (
        <ActionDialog
          title={`Restore ${name}`}
          confirmLabel="Restore"
          run={(dryRun) => restoreWorkload(kind, name, dryRun)}
          onDone={() => {
            setOpen(false)
            void queryClient.invalidateQueries()
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  )
}

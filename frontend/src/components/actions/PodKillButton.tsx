import { useQueryClient } from '@tanstack/react-query'
import { XCircle } from 'lucide-react'
import { useState } from 'react'

import ActionDialog from '@/components/actions/ActionDialog'
import Tooltip from '@/components/ui/Tooltip'
import { deletePod } from '@/lib/api'
import type { Protection } from '@/lib/schemas'

interface Props {
  name: string
  protection: Protection
  readOnly: boolean
  container?: string
  compact?: boolean
}

/**
 * Kubernetes has no "kill this container" API. The button on a container row
 * still deletes the pod, and the plan says so before anyone confirms.
 */
export default function PodKillButton({
  name,
  protection,
  readOnly,
  container,
  compact,
}: Props) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  if (protection.level === 'protected') return null

  const hint = readOnly
    ? 'Read-only mode is on (ARM_READ_ONLY). No action will run.'
    : container
      ? `Kill container ${container} — deletes the whole pod; the controller replaces it`
      : 'Kill this pod immediately. If a controller owns it, a replacement starts within seconds.'

  const title = container ? `Kill container ${container}` : `Kill pod ${name}`

  return (
    <>
      <Tooltip label={hint}>
        <button
          type="button"
          aria-label={title}
          disabled={readOnly}
          onClick={(event) => {
            event.stopPropagation()
            setOpen(true)
          }}
          className={`rounded border border-line bg-cream text-muted hover:text-danger disabled:cursor-not-allowed disabled:opacity-30 ${
            compact ? 'px-1 py-0.5' : 'px-1.5 py-1'
          }`}
        >
          <XCircle size={compact ? 11 : 12} />
        </button>
      </Tooltip>

      {open && (
        <ActionDialog
          title={title}
          confirmLabel={container ? 'Kill container' : 'Kill pod'}
          destructive
          run={(dryRun) => deletePod(name, dryRun, { force: true, container })}
          onDone={() => {
            setOpen(false)
            void queryClient.invalidateQueries()
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

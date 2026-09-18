import { useQueryClient } from '@tanstack/react-query'
import { XCircle } from 'lucide-react'
import { useState } from 'react'

import ActionDialog from '@/components/actions/ActionDialog'
import Tooltip from '@/components/ui/Tooltip'
import { killService } from '@/lib/api'
import type { ServiceDetail } from '@/lib/schemas'

interface Props {
  service: ServiceDetail
  readOnly: boolean
}

export default function ServiceActions({ service, readOnly }: Props) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  if (service.protection.level === 'protected') return null

  const canKill = service.workloads.some(
    (workload) =>
      workload.protection.level !== 'protected' &&
      (workload.desired_replicas > 0 || workload.pod_count > 0),
  )
  if (!canKill) return null

  const hint = readOnly
    ? 'Read-only mode is on (ARM_READ_ONLY). No action will run.'
    : 'Force-delete every pod and scale the workloads to 0 — the service dies immediately'

  return (
    <>
      <Tooltip label={hint}>
        <button
          type="button"
          disabled={readOnly}
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1 rounded border border-line bg-cream px-2 py-1 text-[11px] text-muted hover:text-danger disabled:cursor-not-allowed disabled:opacity-30"
        >
          <XCircle size={12} aria-hidden />
          Kill service
        </button>
      </Tooltip>

      {open && (
        <ActionDialog
          title={`Kill ${service.title}`}
          confirmLabel="Kill the service"
          destructive
          run={(dryRun) => killService(service.name, dryRun)}
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

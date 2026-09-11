import { useQueryClient } from '@tanstack/react-query'
import { Minus, Plus, Power, RotateCw } from 'lucide-react'
import { useState } from 'react'

import ActionDialog from '@/components/actions/ActionDialog'
import { restartWorkload, scaleWorkload, stopWorkload } from '@/lib/api'
import type { Workload } from '@/lib/schemas'

type Open = 'scale' | 'stop' | 'restart' | null

interface Props {
  workload: Workload
  readOnly: boolean
}

export default function WorkloadActions({ workload, readOnly }: Props) {
  const [open, setOpen] = useState<Open>(null)
  const [target, setTarget] = useState(workload.desired_replicas)
  const queryClient = useQueryClient()

  // Protected workloads get no buttons at all; the badge beside them explains
  // why and points at the Database page.
  if (workload.protection.level === 'protected') return null

  const disabled = readOnly
  const hint = readOnly ? 'This instance is read-only (ARM_READ_ONLY).' : undefined

  function done() {
    setOpen(null)
    void queryClient.invalidateQueries()
  }

  return (
    <div className="flex items-center gap-1">
      <div className="flex items-center rounded border border-line bg-cream">
        <Step
          icon={<Minus size={11} />}
          label="one fewer replica"
          disabled={disabled || target <= 0}
          onClick={() => {
            setTarget(Math.max(0, target - 1))
            setOpen('scale')
          }}
        />
        <span className="px-1.5 font-mono text-[11px] text-body">{workload.desired_replicas}</span>
        <Step
          icon={<Plus size={11} />}
          label="one more replica"
          disabled={disabled}
          onClick={() => {
            setTarget(target + 1)
            setOpen('scale')
          }}
        />
      </div>

      <IconButton
        icon={<RotateCw size={12} />}
        label="Rolling restart"
        title={hint ?? 'Replace pods gradually'}
        disabled={disabled}
        onClick={() => setOpen('restart')}
      />
      <IconButton
        icon={<Power size={12} />}
        label="Stop"
        title={hint ?? 'Scale to 0 replicas'}
        disabled={disabled || workload.desired_replicas === 0}
        danger
        onClick={() => setOpen('stop')}
      />

      {open === 'scale' && (
        <ActionDialog
          title={`Scale ${workload.name}`}
          confirmLabel={`Scale to ${target}`}
          run={(dryRun) =>
            scaleWorkload({
              kind: workload.kind,
              name: workload.name,
              replicas: target,
              dryRun,
            })
          }
          onDone={done}
          onClose={() => setOpen(null)}
        />
      )}

      {open === 'restart' && (
        <ActionDialog
          title={`Restart ${workload.name}`}
          confirmLabel="Restart"
          run={(dryRun) => restartWorkload(workload.kind, workload.name, dryRun)}
          onDone={done}
          onClose={() => setOpen(null)}
        />
      )}

      {open === 'stop' && (
        <ActionDialog
          title={`Stop ${workload.name}`}
          confirmLabel="Stop the service"
          destructive
          run={(dryRun) => stopWorkload(workload.kind, workload.name, dryRun)}
          onDone={done}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function Step({
  icon,
  label,
  disabled,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="px-1.5 py-1 text-muted hover:text-arango disabled:cursor-not-allowed disabled:opacity-30"
    >
      {icon}
    </button>
  )
}

function IconButton({
  icon,
  label,
  title,
  disabled,
  danger,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  title?: string
  disabled: boolean
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      disabled={disabled}
      onClick={onClick}
      className={`rounded border border-line bg-cream px-1.5 py-1 disabled:cursor-not-allowed disabled:opacity-30 ${
        danger ? 'text-muted hover:text-danger' : 'text-muted hover:text-arango'
      }`}
    >
      {icon}
    </button>
  )
}

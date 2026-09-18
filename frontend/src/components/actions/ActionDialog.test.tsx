import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import ActionDialog from '@/components/actions/ActionDialog'
import { killPlan, okResult } from '@/test/fixtures'
import type { ActionResult } from '@/lib/schemas'

describe('ActionDialog', () => {
  it('runs a dry-run first and keeps confirm disabled until the name is typed', async () => {
    const user = userEvent.setup()
    const run = vi.fn(async (dryRun: boolean) => okResult(killPlan, dryRun))
    const onDone = vi.fn()

    render(
      <ActionDialog
        title="Kill worker"
        confirmLabel="Kill the service"
        destructive
        run={run}
        onDone={onDone}
        onClose={() => undefined}
      />,
    )

    expect(await screen.findByText(/force-deleted immediately/)).toBeInTheDocument()
    expect(run).toHaveBeenCalledWith(true)

    const confirm = screen.getByRole('button', { name: 'Kill the service' })
    expect(confirm).toBeDisabled()

    await user.type(
      screen.getByRole('textbox'),
      'arangodb-file-parser-worker-default',
    )
    expect(confirm).toBeDisabled()

    await user.click(screen.getByRole('checkbox'))
    expect(confirm).toBeEnabled()

    await user.click(confirm)
    expect(run).toHaveBeenCalledWith(false)
    expect(onDone).toHaveBeenCalled()
  })

  it('shows a blocked reason instead of asking for confirmation', async () => {
    const blocked: ActionResult = {
      executed: false,
      dry_run: true,
      plan: null,
      blocked_reason: 'protected',
      detail: 'This workload is managed by an operator.',
      remediation: 'Resize this from the Database page.',
    }
    render(
      <ActionDialog
        title="Kill dbserver"
        confirmLabel="Kill"
        run={async () => blocked}
        onDone={() => undefined}
        onClose={() => undefined}
      />,
    )

    expect(await screen.findByText(/managed by an operator/)).toBeInTheDocument()
    expect(screen.getByText(/Database page/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Kill' })).not.toBeInTheDocument()
  })
})

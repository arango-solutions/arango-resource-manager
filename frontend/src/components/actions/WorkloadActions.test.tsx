import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import WorkloadActions from '@/components/actions/WorkloadActions'
import { killPlan, normalWorkload, okResult, protectedWorkload } from '@/test/fixtures'

vi.mock('@/lib/api', () => ({
  killWorkload: vi.fn(async (_kind: string, _name: string, dryRun: boolean) =>
    okResult(killPlan, dryRun),
  ),
  restartWorkload: vi.fn(),
  restoreWorkload: vi.fn(),
  scaleWorkload: vi.fn(),
  stopWorkload: vi.fn(),
}))

function mount(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('WorkloadActions', () => {
  it('hides every button on a protected workload', () => {
    mount(<WorkloadActions workload={protectedWorkload} readOnly={false} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('disables kill while read-only', () => {
    mount(<WorkloadActions workload={normalWorkload} readOnly />)
    expect(screen.getByRole('button', { name: 'Kill' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled()
  })

  it('still offers kill after the workload is scaled to zero', () => {
    mount(
      <WorkloadActions
        workload={{ ...normalWorkload, desired_replicas: 0, ready_replicas: 0, pod_count: 2 }}
        readOnly={false}
      />,
    )
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kill' })).toBeEnabled()
  })

  it('opens the kill dialog from the kill button', async () => {
    const user = userEvent.setup()
    mount(<WorkloadActions workload={normalWorkload} readOnly={false} />)

    await user.click(screen.getByRole('button', { name: 'Kill' }))
    expect(await screen.findByText(/Kill arangodb-file-parser-worker-default/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kill the service' })).toBeDisabled()
  })
})

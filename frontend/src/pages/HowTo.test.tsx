import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import SideMenu from '@/components/layout/SideMenu'
import HowTo from '@/pages/HowTo'

describe('How-to', () => {
  it('is reachable from the side menu', () => {
    render(
      <MemoryRouter>
        <SideMenu healthy />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'How-to' })).toHaveAttribute('href', '/howto')
  })

  it('covers the actions a user can take and links into the pages that do them', () => {
    render(
      <MemoryRouter>
        <HowTo />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'How to use this tool' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Scale, stop, kill, restart' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Resize the database' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'When a button is missing' })).toBeInTheDocument()

    expect(screen.getAllByRole('link', { name: 'Capacity' })[0]).toHaveAttribute('href', '/capacity')
    expect(screen.getAllByRole('link', { name: 'Database' })[0]).toHaveAttribute('href', '/database')
    expect(screen.getAllByRole('link', { name: 'Settings' })[0]).toHaveAttribute('href', '/settings')
  })

  it('jumps to a section from the table of contents', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    HTMLElement.prototype.scrollIntoView = scrollIntoView

    render(
      <MemoryRouter>
        <HowTo />
      </MemoryRouter>,
    )

    await user.click(screen.getAllByRole('link', { name: 'Kill a pod' })[0])
    expect(scrollIntoView).toHaveBeenCalled()
    expect(document.getElementById('pods')).toBeInTheDocument()
  })
})

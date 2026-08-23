import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('AgentForge operations console', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend unavailable')))
  })

  it('renders the task dashboard and approval queue', async () => {
    render(<App />)
    expect((await screen.findAllByText('Release v2.0 Verification')).length).toBeGreaterThan(0)
    expect(screen.getByText('Approval queue')).toBeInTheDocument()
    expect(screen.getByText('Demo data preview · connect the FastAPI backend to use live task data.')).toBeInTheDocument()
  })

  it('opens the approval center from the dashboard', async () => {
    render(<App />)
    fireEvent.click((await screen.findAllByRole('button', { name: /Review approvals/i }))[0])
    expect(screen.getByRole('heading', { name: 'Approval Center' })).toBeInTheDocument()
    expect(screen.getByText('This is what the Agent will execute.')).toBeInTheDocument()
    expect(screen.getByText('test_verification')).toBeInTheDocument()
    expect(screen.getByText(/Resolved tool: test_run/i)).toBeInTheDocument()
    expect(screen.getByText(/profile: smoke/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Registry fingerprint:/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AgentTimeline } from './AgentTimeline'

describe('Agent timeline presentation', () => {
  it('renders safe structured lifecycle entries and raw execution status', () => {
    render(<AgentTimeline entries={[{ id: 'goal', kind: 'GOAL_RECEIVED', timestamp: '2026-08-26T10:00:00Z', status: 'CREATED', summary: 'RAW GOAL' }, { id: 'failure', kind: 'TOOL_EXECUTION_COMPLETED', timestamp: '2026-08-26T10:01:00Z', status: 'FAILED', summary: 'test_run · run_profile: RAW ERROR' }, { id: 'waiting', kind: 'WAITING_APPROVAL', timestamp: '2026-08-26T10:02:00Z', planVersion: 2, status: 'PENDING', summary: 'Waiting for approval' }]} />)
    expect(screen.getByText('Goal received')).toBeInTheDocument()
    expect(screen.getByText('Tool execution completed')).toBeInTheDocument()
    expect(screen.getByText(/RAW ERROR/)).toBeInTheDocument()
    expect(screen.getByText('Plan v2')).toBeInTheDocument()
    expect(screen.queryByText(/thinking|reasoning|chain.of.thought/i)).not.toBeInTheDocument()
  })
})

import { afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AgentTimeline } from './AgentTimeline'
import { i18n } from '../i18n'

afterEach(async () => {
  cleanup()
  await i18n.changeLanguage('en-US')
})

describe('Agent timeline presentation', () => {
  it('renders safe structured lifecycle entries and raw execution status', () => {
    render(<AgentTimeline entries={[{ id: 'goal', kind: 'GOAL_RECEIVED', timestamp: '2026-08-26T10:00:00Z', status: 'CREATED', summary: 'RAW GOAL' }, { id: 'failure', kind: 'TOOL_EXECUTION_COMPLETED', timestamp: '2026-08-26T10:01:00Z', status: 'FAILED', summary: 'test_run · run_profile: RAW ERROR' }, { id: 'waiting', kind: 'WAITING_APPROVAL', timestamp: '2026-08-26T10:02:00Z', planVersion: 2, status: 'PENDING', summary: 'Waiting for approval' }]} />)
    expect(screen.getByText('Goal received')).toBeInTheDocument()
    expect(screen.getByText('Tool execution completed')).toBeInTheDocument()
    expect(screen.getByText(/RAW ERROR/)).toBeInTheDocument()
    expect(screen.getByText('Plan v2')).toBeInTheDocument()
    expect(screen.queryByText(/thinking|reasoning|chain.of.thought/i)).not.toBeInTheDocument()
  })

  it('keeps raw technical payload available behind expandable details', () => {
    render(<AgentTimeline entries={[{ id: 'raw', kind: 'OBSERVATION_RECORDED', timestamp: '2026-08-26T10:00:00Z', status: 'FAILED', summary: 'Observation recorded', raw: { raw_error: 'RAW ERROR', path: 'src/raw.py' } }]} />)
    expect(screen.queryByText('RAW ERROR')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show technical details' }))
    expect(screen.getByText(/RAW ERROR/)).toBeInTheDocument()
    expect(screen.getByText(/src\/raw.py/)).toBeInTheDocument()
  })

  it('keeps lifecycle event title and timestamp in separate readable fields', () => {
    render(<AgentTimeline entries={[{ id: 'goal', kind: 'GOAL_RECEIVED', timestamp: '2026-08-26T10:00:00Z', status: 'CREATED', summary: 'Goal received' }]} />)

    const row = screen.getByRole('listitem')
    expect(row).toHaveClass('agent-timeline-row')
    expect(row.querySelector('time')).toBeInTheDocument()
    expect(row.querySelector('.agent-timeline-heading')).toHaveTextContent('Goal received')
  })

  it('localizes event labels while leaving technical status values intact', async () => {
    await i18n.changeLanguage('zh-CN')
    render(<AgentTimeline entries={[{ id: 'goal', kind: 'GOAL_RECEIVED', timestamp: '2026-08-26T10:00:00Z', status: 'CREATED', summary: 'Goal received' }]} />)

    expect(screen.getByText('已收到目标')).toBeInTheDocument()
    expect(screen.getByText('CREATED')).toBeInTheDocument()
    expect(screen.getByText('Goal received')).toBeInTheDocument()
  })
})

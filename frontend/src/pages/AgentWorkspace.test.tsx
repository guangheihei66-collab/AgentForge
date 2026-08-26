import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AgentWorkspace } from './AgentWorkspace'
import type { ProjectSummary } from '../types'

const projects: ProjectSummary[] = [{ id: 'project-1', name: 'AgentForge', description: 'Repository', workspace_root: 'D:/AgentForge', environment: 'development', status: 'ACTIVE', allowed_capability_ids: ['repository_state'], config_version: 1, recent_task_count: 0, created_at: '2026-08-26T10:00:00Z', updated_at: '2026-08-26T10:00:00Z' }]

describe('Repository Analyst Agent workspace', () => {
  it('requires an explicit Project and preserves the raw Goal on start', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined)
    render(<AgentWorkspace projects={projects} planning={false} error={null} onStart={onStart} />)
    const goal = 'Check this repository for release risks.\nKeep this exact text.'
    fireEvent.change(screen.getByLabelText('Goal'), { target: { value: goal } })
    fireEvent.click(screen.getByRole('button', { name: 'Start Agent' }))
    expect(onStart).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Project'), { target: { value: 'project-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start Agent' }))
    await waitFor(() => expect(onStart).toHaveBeenCalledWith('project-1', goal))
  })

  it('shows transient Planning while the real lifecycle request is unresolved', () => {
    render(<AgentWorkspace projects={projects} planning error={null} onStart={vi.fn()} />)
    expect(screen.getByText('Planning...')).toBeInTheDocument()
    expect(screen.queryByText('Plan created')).not.toBeInTheDocument()
    expect(screen.queryByText('Waiting for approval')).not.toBeInTheDocument()
  })
})

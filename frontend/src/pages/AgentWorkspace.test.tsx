import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentWorkspace } from './AgentWorkspace'
import type { ProjectSummary } from '../types'

const projects: ProjectSummary[] = [{ id: 'project-1', name: 'AgentForge', description: 'Repository', workspace_root: 'D:/AgentForge', environment: 'development', status: 'ACTIVE', allowed_capability_ids: ['repository_state'], config_version: 1, recent_task_count: 0, created_at: '2026-08-26T10:00:00Z', updated_at: '2026-08-26T10:00:00Z' }]
const task = { id: 'task-1', project_id: 'project-1', title: 'Repository Analyst Agent', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'WAITING_APPROVAL' as const, created_at: '', updated_at: '' }

describe('Repository Analyst Agent workspace', () => {
  afterEach(() => cleanup())

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

  it('shows current run identity, authoritative status, and only matching approval', () => {
    const selectedTask = { ...task, id: 'task-current', project_id: 'project-1', status: 'WAITING_APPROVAL' as const }
    const authority = { project_id: 'project-1', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'd:/agentforge' }
    const plan = { id: 'plan-current', version: 1, validation_status: 'VALID', created_at: '', plan_json: { schema_version: 2 as const, steps: [], resolved_steps: [], project_authority: authority } }
    const approval = { id: 'approval-current', task_id: selectedTask.id, task_title: selectedTask.title, plan_id: plan.id, plan_version: 1, decision: 'PENDING', requested_by: 'operator', created_at: '', plan_json: plan.plan_json, resolved_snapshot: { schema_version: 2 as const, project_authority: authority, steps: [] } }
    render(<AgentWorkspace projects={projects} planning={false} error={null} onStart={vi.fn()} task={selectedTask} detail={{ task: selectedTask, plans: [plan], approvals: [], executions: [], evidence: [], audit: [] }} report={{ task: selectedTask, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 }} approvals={[{ ...approval, task_id: 'other-task' }, approval]} onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText('task-current')).toBeInTheDocument()
    expect(screen.getAllByText('Waiting for approval').length).toBeGreaterThan(0)
    expect(screen.getAllByText('AgentForge').length).toBeGreaterThan(0)
    expect(screen.getByText('Approval required')).toBeInTheDocument()
  })

})

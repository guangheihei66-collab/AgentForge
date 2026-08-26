import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api } from './api/client'
import type { ApprovalSnapshot, ProjectAuthority, TaskDetail } from './types'

const task = { id: 'task-current', project_id: 'project-1', title: 'Repository Analyst Agent', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'WAITING_APPROVAL' as const, created_at: '', updated_at: '' }
const project = { id: 'project-1', name: 'AgentForge', description: null, workspace_root: 'D:/AgentForge', environment: 'development', status: 'ACTIVE' as const, allowed_capability_ids: ['repository_state'], config_version: 1, recent_task_count: 0, created_at: '', updated_at: '' }
const authority: ProjectAuthority = { project_id: project.id, config_version: 1, authority_fingerprint: 'fingerprint', canonical_workspace_root: project.workspace_root }
const snapshot: ApprovalSnapshot = { schema_version: 2, project_authority: authority, steps: [] }
const plan = { id: 'plan-1', version: 1, validation_status: 'VALID' as const, created_at: '', plan_json: { schema_version: 2 as const, steps: [], resolved_steps: [], project_authority: authority } }
const pending = { id: 'approval-1', approval_id: 'approval-1', task_id: task.id, task_title: task.title, plan_id: plan.id, plan_version: 1, decision: 'PENDING' as const, requested_by: 'operator', created_at: '', plan_json: plan.plan_json, resolved_snapshot: snapshot }

describe('Agent approval-to-execution wiring', () => {
  beforeEach(() => {
    let approved = false
    const storage = { getItem: () => task.id, setItem: vi.fn(), removeItem: vi.fn() }
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    vi.spyOn(api, 'listTasks').mockResolvedValue([task])
    vi.spyOn(api, 'getPendingApprovals').mockResolvedValue([pending])
    vi.spyOn(api, 'listProjects').mockResolvedValue([project])
    vi.spyOn(api, 'getProviderStatus').mockResolvedValue({ provider: 'mock', model: 'deterministic-mock', configured: true, credential_configured: false, connection_status: 'not tested' })
    vi.spyOn(api, 'getReport').mockResolvedValue({ task, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 })
    vi.spyOn(api, 'getTaskDetail').mockImplementation(async (): Promise<TaskDetail> => ({ task: approved ? { ...task, status: 'RUNNING' } : task, plans: [plan], approvals: [{ ...pending, approver: 'operator', decision: approved ? 'APPROVED' : 'PENDING' }], executions: [], evidence: [], audit: [] }))
    vi.spyOn(api, 'approve').mockImplementation(async () => { approved = true; return { ...pending, decision: 'APPROVED' } })
    vi.spyOn(api, 'executeTask').mockResolvedValue({ ...task, status: 'RUNNING' })
  })

  afterEach(() => vi.restoreAllMocks())

  it('approves the matching current plan before executing it exactly once', async () => {
    render(<App />)
    fireEvent.click((await screen.findAllByText(task.title))[0])
    fireEvent.click(screen.getByRole('button', { name: 'Agent' }))
    await waitFor(() => expect(api.getTaskDetail).toHaveBeenCalledWith(task.id))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(api.executeTask).toHaveBeenCalledTimes(1))
    expect(api.approve).toHaveBeenCalledTimes(1)
    expect(vi.mocked(api.approve).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.executeTask).mock.invocationCallOrder[0])
    expect(api.executeTask).toHaveBeenCalledWith(task.id)
  })
})

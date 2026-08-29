import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api } from './api/client'
import type { ApprovalSnapshot, ProjectAuthority, TaskDetail } from './types'

const task = { id: 'task-current', project_id: 'project-1', title: 'Repository Analyst Agent', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'WAITING_APPROVAL' as const, created_at: '', updated_at: '' }
const staleTask = { id: 'task-stale', project_id: 'project-1', title: 'Stale historical task', goal: 'OLD GOAL', workspace: 'D:/AgentForge', status: 'RUNNING' as const, created_at: '', updated_at: '' }
const project = { id: 'project-1', name: 'AgentForge', description: null, workspace_root: 'D:/AgentForge', environment: 'development', status: 'ACTIVE' as const, allowed_capability_ids: ['repository_state'], config_version: 1, recent_task_count: 0, created_at: '', updated_at: '' }
const authority: ProjectAuthority = { project_id: project.id, config_version: 1, authority_fingerprint: 'fingerprint', canonical_workspace_root: project.workspace_root }
const snapshot: ApprovalSnapshot = { schema_version: 2, project_authority: authority, steps: [] }
const plan = { id: 'plan-1', version: 1, validation_status: 'VALID' as const, created_at: '', plan_json: { schema_version: 2 as const, steps: [], resolved_steps: [], project_authority: authority } }
const pending = { id: 'approval-1', approval_id: 'approval-1', task_id: task.id, task_title: task.title, plan_id: plan.id, plan_version: 1, decision: 'PENDING' as const, requested_by: 'operator', created_at: '', plan_json: plan.plan_json, resolved_snapshot: snapshot }
const nonAgentPending = { ...pending, task_title: 'Repository Analyst Agent', resolved_snapshot: null }

describe('Agent approval-to-execution wiring', () => {
  beforeEach(() => {
    let approved = false
    const storage = { getItem: () => task.id, setItem: vi.fn(), removeItem: vi.fn() }
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    vi.spyOn(api, 'listTasks').mockResolvedValue([task])
    vi.spyOn(api, 'getPendingApprovals').mockImplementation(async () => approved ? [] : [pending])
    vi.spyOn(api, 'listProjects').mockResolvedValue([project])
    vi.spyOn(api, 'getProviderStatus').mockResolvedValue({ provider: 'mock', model: 'deterministic-mock', configured: true, credential_configured: false, connection_status: 'not tested' })
    vi.spyOn(api, 'getReport').mockResolvedValue({ task, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 })
    vi.spyOn(api, 'getTaskDetail').mockImplementation(async (): Promise<TaskDetail> => ({ task: approved ? { ...task, status: 'RUNNING' } : task, plans: [plan], approvals: [{ ...pending, approver: 'operator', decision: approved ? 'APPROVED' : 'PENDING' }], executions: [], evidence: [], audit: [] }))
    vi.spyOn(api, 'approve').mockResolvedValue({ ...pending, decision: 'APPROVED' })
    vi.spyOn(api, 'approveAndExecuteTask').mockImplementation(async () => {
      approved = true
      return { task_id: task.id, plan_id: plan.id, plan_version: plan.version, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null }
    })
    vi.spyOn(api, 'executeTask').mockResolvedValue({ ...task, status: 'RUNNING' })
  })

  afterEach(() => { cleanup(); vi.restoreAllMocks() })

  it('sends one bound approval-and-execute command from the Agent Workspace', async () => {
    render(<App />)
    fireEvent.click((await screen.findAllByText(task.title))[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Agent' })[0])
    await waitFor(() => expect(api.getTaskDetail).toHaveBeenCalledWith(task.id))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve & Execute' }))
    await waitFor(() => expect(api.approveAndExecuteTask).toHaveBeenCalledTimes(1))
    expect(api.approve).not.toHaveBeenCalled()
    expect(api.executeTask).not.toHaveBeenCalled()
    expect(api.approveAndExecuteTask).toHaveBeenCalledWith(task.id, {
      approval_id: 'approval-1',
      plan_id: 'plan-1',
      plan_version: 1,
      actor: 'operator',
      language: 'en-US',
    })
  })

  it('routes an already-approved Agent retry through the composite command', async () => {
    const runningTask = { ...task, status: 'RUNNING' as const }
    vi.mocked(api.listTasks).mockResolvedValue([runningTask])
    vi.mocked(api.getPendingApprovals).mockResolvedValue([])
    vi.mocked(api.getTaskDetail).mockResolvedValue({
      task: runningTask,
      plans: [plan],
      approvals: [{ ...pending, approver: 'operator', decision: 'APPROVED' }],
      executions: [],
      evidence: [],
      audit: [],
    })
    vi.mocked(api.getReport).mockResolvedValue({ task: runningTask, readiness: 'PENDING', summary: 'Awaiting execution', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 })
    vi.mocked(api.approveAndExecuteTask).mockResolvedValue({ task_id: task.id, plan_id: plan.id, plan_version: plan.version, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null })
    vi.mocked(api.executeTask).mockClear()

    render(<App />)
    fireEvent.click((await screen.findAllByText(task.title))[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Agent' })[0])
    await waitFor(() => expect(api.getTaskDetail).toHaveBeenCalledWith(task.id))
    fireEvent.click(await screen.findByRole('button', { name: 'Resume approved execution' }))
    await waitFor(() => expect(api.approveAndExecuteTask).toHaveBeenCalledTimes(1))
    expect(api.executeTask).not.toHaveBeenCalled()
    expect(api.approveAndExecuteTask).toHaveBeenCalledWith(task.id, {
      approval_id: 'approval-1',
      plan_id: 'plan-1',
      plan_version: 1,
      actor: 'operator',
      language: 'en-US',
    })
  })

  it('keeps Global Approval approval-only for a non-Agent approval', async () => {
    vi.mocked(api.getPendingApprovals).mockResolvedValue([nonAgentPending])
    render(<App />)
    fireEvent.click(screen.getAllByRole('button', { name: /Approvals/i })[0])

    fireEvent.click(await screen.findByRole('button', { name: 'Approve only' }))

    await waitFor(() => expect(api.approve).toHaveBeenCalledTimes(1))
    expect(api.approve).toHaveBeenCalledWith('approval-1')
    expect(api.approveAndExecuteTask).not.toHaveBeenCalled()
    expect(api.executeTask).not.toHaveBeenCalled()
  })

  it('opens the selected task in Agent Workspace without a backend mutation', async () => {
    render(<App />)
    fireEvent.click(screen.getAllByRole('button', { name: /Approvals/i })[0])

    expect(screen.queryByRole('button', { name: 'Approve only' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Open in Agent Workspace' }))

    expect(await screen.findByRole('heading', { name: 'Agent workspace' })).toBeInTheDocument()
    expect(await screen.findByText(task.id)).toBeInTheDocument()
    expect(api.approve).not.toHaveBeenCalled()
    expect(api.approveAndExecuteTask).not.toHaveBeenCalled()
    expect(api.executeTask).not.toHaveBeenCalled()
  })

  it('switches from a restored historical task to the approval task before rendering Agent controls', async () => {
    const storage = { getItem: () => staleTask.id, setItem: vi.fn(), removeItem: vi.fn() }
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage })
    vi.mocked(api.listTasks).mockResolvedValue([staleTask, task])
    vi.mocked(api.getTaskDetail).mockImplementation(async (id): Promise<TaskDetail> => ({
      task: id === task.id ? task : staleTask,
      plans: [plan],
      approvals: id === task.id ? [{ ...pending, approver: 'operator', decision: 'PENDING' }] : [],
      executions: [],
      evidence: [],
      audit: [],
    }))
    vi.mocked(api.getReport).mockImplementation(async (id) => ({ task: id === task.id ? task : staleTask, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 }))

    render(<App />)
    await waitFor(() => expect(api.getTaskDetail).toHaveBeenCalledWith(staleTask.id))
    fireEvent.click(screen.getAllByRole('button', { name: /Approvals/i })[0])
    fireEvent.click(await screen.findByRole('button', { name: 'Open in Agent Workspace' }))

    expect(await screen.findByText(task.id)).toBeInTheDocument()
    expect(screen.queryByText(staleTask.id)).not.toBeInTheDocument()
  })
})

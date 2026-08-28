import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useOperations } from './useOperations'
import type { ApprovalQueueItem } from '../types'

const apiMock = vi.hoisted(() => ({
  listTasks: vi.fn(), getPendingApprovals: vi.fn(), listProjects: vi.fn(), getTaskDetail: vi.fn(), getReport: vi.fn(), getProviderStatus: vi.fn(), createTask: vi.fn(), createPlan: vi.fn(), createApproval: vi.fn(), approve: vi.fn(), reject: vi.fn(), executeTask: vi.fn(), approveAndExecuteTask: vi.fn(),
}))
vi.mock('../api/client', () => ({ api: apiMock }))

const project = { id: 'project-1', name: 'AgentForge', description: null, workspace_root: 'D:/AgentForge', environment: 'development', status: 'ACTIVE', allowed_capability_ids: ['repository_state'], config_version: 1, recent_task_count: 0, created_at: '2026-08-26T10:00:00Z', updated_at: '2026-08-26T10:00:00Z' }
const task = { id: 'task-1', project_id: 'project-1', title: 'Repository Analyst Agent', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'WAITING_APPROVAL', created_at: '2026-08-26T10:00:00Z', updated_at: '2026-08-26T10:00:00Z' }
const authority = { project_id: 'project-1', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/AgentForge' }
const plan = { id: 'plan-1', task_id: 'task-1', version: 1, validation_status: 'VALID', created_at: '2026-08-26T10:00:01Z', plan_json: { schema_version: 2 as const, steps: [], resolved_steps: [], project_authority: authority } }
const approval = { id: 'approval-1', task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, decision: 'PENDING', approver: 'pending', reason: null, resolved_snapshot: { schema_version: 2 as const, project_authority: authority, steps: [] }, created_at: '2026-08-26T10:00:02Z' }
const detail = { task, plans: [plan], approvals: [approval], executions: [], evidence: [], audit: [] }
const report = { task, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 0, execution_count: 0 }
const queueItem: ApprovalQueueItem = { id: 'approval-1', approval_id: 'approval-1', task_id: 'task-1', task_title: task.title, plan_id: 'plan-1', plan_version: 1, decision: 'PENDING', requested_by: 'operator', created_at: '2026-08-26T10:00:02Z', plan_json: plan.plan_json, resolved_snapshot: { schema_version: 2, project_authority: authority, steps: [] } }

describe('Agent Task -> Plan -> Approval orchestration', () => {
  const storage = new Map<string, string>()
  beforeEach(() => {
    vi.clearAllMocks()
    storage.clear()
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) } })
    apiMock.listTasks.mockResolvedValue([])
    apiMock.getPendingApprovals.mockResolvedValue([])
    apiMock.listProjects.mockResolvedValue([project])
    apiMock.getProviderStatus.mockResolvedValue({ provider: 'mock', model: 'deterministic-mock', configured: true, credential_configured: false, connection_status: 'not tested' })
    apiMock.getTaskDetail.mockResolvedValue({ ...detail, approvals: [] })
    apiMock.getReport.mockResolvedValue(report)
    apiMock.createTask.mockResolvedValue(task)
    apiMock.createPlan.mockResolvedValue(plan)
    apiMock.createApproval.mockResolvedValue(approval)
  })

  it('creates Task, calls Plan with returned task ID, creates matching Approval, then refreshes truth', async () => {
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL') })
    expect(apiMock.createTask).toHaveBeenCalledWith({ project_id: 'project-1', title: 'Repository Analyst Agent', goal: 'RAW GOAL' })
    expect(apiMock.createPlan).toHaveBeenCalledWith('task-1')
    expect(apiMock.createApproval).toHaveBeenCalledWith('task-1', 'plan-1', 1)
    expect(apiMock.createPlan.mock.invocationCallOrder[0]).toBeGreaterThan(apiMock.createTask.mock.invocationCallOrder[0])
    expect(apiMock.createApproval.mock.invocationCallOrder[0]).toBeGreaterThan(apiMock.createPlan.mock.invocationCallOrder[0])
    expect(apiMock.executeTask).not.toHaveBeenCalled()
  })

  it('does not let a polling refresh cancel Task creation before planning', async () => {
    let releaseTask!: (value: typeof task) => void
    apiMock.createTask.mockReturnValueOnce(new Promise(resolve => { releaseTask = resolve }))
    const { result } = renderHook(() => useOperations())
    let creation!: Promise<unknown>
    await act(async () => { creation = result.current.createAgentTask('project-1', 'RAW GOAL'); await Promise.resolve() })
    await act(async () => { void result.current.refresh(); await Promise.resolve(); releaseTask(task) })
    await waitFor(() => expect(apiMock.createPlan).toHaveBeenCalledWith('task-1'))
    await act(async () => { await creation })
  })

  it('does not duplicate an authoritative matching Approval', async () => {
    apiMock.getTaskDetail.mockResolvedValue(detail)
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL') })
    expect(apiMock.createApproval).not.toHaveBeenCalled()
  })

  it('refreshes after ambiguous Approval failure and accepts only authoritative matching state', async () => {
    apiMock.createApproval.mockRejectedValueOnce(new Error('network failure'))
    apiMock.getTaskDetail.mockResolvedValueOnce({ ...detail, approvals: [] }).mockResolvedValueOnce(detail)
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL').catch(() => undefined) })
    await waitFor(() => expect(apiMock.getTaskDetail).toHaveBeenCalledTimes(3))
    expect(apiMock.createApproval).toHaveBeenCalledTimes(1)
  })

  it('does not create Approval or execute when planning fails', async () => {
    apiMock.createPlan.mockRejectedValueOnce(new Error('LLM planning failed: INVALID_RESPONSE'))
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL').catch(() => undefined) })
    expect(apiMock.createApproval).not.toHaveBeenCalled()
    expect(apiMock.executeTask).not.toHaveBeenCalled()
    expect(result.current.agentError).toContain('INVALID_RESPONSE')
  })

  it('resumes only after an authoritative current Plan is approved', async () => {
    apiMock.getTaskDetail.mockResolvedValue({ ...detail, approvals: [{ ...approval, decision: 'APPROVED' }] })
    apiMock.approveAndExecuteTask.mockResolvedValue({ task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null })
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL') })
    await act(async () => { await result.current.executeAgentTask() })
    expect(apiMock.approveAndExecuteTask).toHaveBeenCalledWith('task-1', {
      approval_id: 'approval-1',
      plan_id: 'plan-1',
      plan_version: 1,
      actor: 'operator',
    })
    expect(apiMock.executeTask).not.toHaveBeenCalled()
  })

  it('uses one composite command and never starts Agent execution through the old two-hop APIs', async () => {
    storage.set('agentforge.agent.currentTaskId', 'task-1')
    apiMock.getTaskDetail.mockResolvedValue(detail)
    apiMock.approveAndExecuteTask.mockResolvedValue({ task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null })
    const { result } = renderHook(() => useOperations())

    await act(async () => { await result.current.approveAndExecuteAgentTask(queueItem) })

    expect(apiMock.approveAndExecuteTask).toHaveBeenCalledTimes(1)
    expect(apiMock.approveAndExecuteTask).toHaveBeenCalledWith('task-1', { approval_id: 'approval-1', plan_id: 'plan-1', plan_version: 1, actor: 'operator' })
    expect(apiMock.approve).not.toHaveBeenCalled()
    expect(apiMock.executeTask).not.toHaveBeenCalled()
  })

  it('sends the composite command before a display-only refresh can fail', async () => {
    storage.set('agentforge.agent.currentTaskId', 'task-1')
    apiMock.approveAndExecuteTask.mockResolvedValue({ task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null })
    apiMock.getTaskDetail.mockRejectedValue(new Error('refresh failed'))
    const { result } = renderHook(() => useOperations())

    await act(async () => { await result.current.approveAndExecuteAgentTask(queueItem).catch(() => undefined) })

    expect(apiMock.approveAndExecuteTask).toHaveBeenCalledTimes(1)
  })

  it('renders a safe Agent error when the composite command fails', async () => {
    storage.set('agentforge.agent.currentTaskId', 'task-1')
    apiMock.approveAndExecuteTask.mockRejectedValue(new Error('secret provider payload'))
    const { result } = renderHook(() => useOperations())

    await act(async () => { await result.current.approveAndExecuteAgentTask(queueItem).catch(() => undefined) })

    expect(result.current.agentError).toBe('The Agent could not approve and start execution.')
    expect(result.current.agentError).not.toContain('secret provider payload')
  })

  it('does not issue a duplicate composite command while the first is in flight', async () => {
    storage.set('agentforge.agent.currentTaskId', 'task-1')
    let release!: (value: unknown) => void
    apiMock.approveAndExecuteTask.mockReturnValue(new Promise(resolve => { release = resolve }))
    const { result } = renderHook(() => useOperations())
    let first!: Promise<void>
    let second!: Promise<void>
    await act(async () => {
      first = result.current.approveAndExecuteAgentTask(queueItem)
      second = result.current.approveAndExecuteAgentTask(queueItem)
      release({ task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1, observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null })
      await Promise.all([first, second])
    })

    expect(apiMock.approveAndExecuteTask).toHaveBeenCalledTimes(1)
  })

  it('keeps the newly-created run when the mount list response arrives late', async () => {
    let releaseList!: (value: unknown[]) => void
    apiMock.listTasks.mockReturnValueOnce(new Promise(resolve => { releaseList = resolve }))
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.createAgentTask('project-1', 'RAW GOAL') })
    await act(async () => { releaseList([ { ...task, id: 'historical-task' } ]) })
    expect(result.current.selectedId).toBe('task-1')
  })

  it('restores the persisted Agent run instead of selecting unrelated history', async () => {
    storage.set('agentforge.agent.currentTaskId', 'task-1')
    apiMock.getTaskDetail.mockResolvedValue(detail)
    const { result } = renderHook(() => useOperations())
    await waitFor(() => expect(result.current.selectedId).toBe('task-1'))
    expect(apiMock.getTaskDetail).toHaveBeenCalledWith('task-1')
  })

  it('marks clean Agent state live without selecting historical task data', async () => {
    apiMock.listTasks.mockResolvedValue([{ ...task, id: 'historical-task' }])
    const { result } = renderHook(() => useOperations())
    await waitFor(() => expect(result.current.live).toBe(true))
    expect(result.current.selectedId).toBeUndefined()
    expect(result.current.projects).toEqual([project])
    expect(apiMock.getTaskDetail).toHaveBeenCalledWith('historical-task')
  })

  it('clears an invalid restored Agent task while keeping base data live', async () => {
    storage.set('agentforge.agent.currentTaskId', 'missing-task')
    apiMock.getTaskDetail.mockRejectedValueOnce(new Error('Task not found'))
    apiMock.getReport.mockRejectedValueOnce(new Error('Task not found'))
    const { result } = renderHook(() => useOperations())
    await waitFor(() => expect(result.current.live).toBe(true))
    expect(result.current.selectedId).toBeUndefined()
    expect(globalThis.localStorage.getItem('agentforge.agent.currentTaskId')).toBeNull()
    expect(result.current.projects).toEqual([project])
  })

  it('recovers live authoritative data after an initial read failure without creating anything', async () => {
    apiMock.listTasks.mockRejectedValueOnce(new Error('backend unavailable')).mockResolvedValue([])
    apiMock.listProjects.mockRejectedValueOnce(new Error('backend unavailable')).mockResolvedValue([project])
    const { result } = renderHook(() => useOperations())
    await waitFor(() => expect(apiMock.listTasks).toHaveBeenCalled())
    expect(result.current.live).toBe(false)
    await act(async () => { await result.current.refresh() })
    expect(result.current.live).toBe(true)
    expect(result.current.projects).toEqual([project])
    expect(result.current.tasks).toEqual([])
    expect(apiMock.createTask).not.toHaveBeenCalled()
  })

  it('keeps live after an older refresh fails following a newer success', async () => {
    let rejectOld!: (error: Error) => void
    apiMock.listTasks.mockReturnValueOnce(new Promise((_resolve, reject) => { rejectOld = reject })).mockResolvedValue([])
    apiMock.listProjects.mockReturnValueOnce(new Promise(() => undefined)).mockResolvedValue([project])
    const { result } = renderHook(() => useOperations())
    await act(async () => { await result.current.refresh() })
    await waitFor(() => expect(result.current.live).toBe(true))
    await act(async () => { rejectOld(new Error('late stale refresh failure')) })
    expect(result.current.live).toBe(true)
  })
})

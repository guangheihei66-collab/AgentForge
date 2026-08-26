import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Approval, ApprovalQueueItem, CapabilityPlanStep, Plan, ProjectDetail, ProjectSummary, ProviderStatus, Report, ResolvedExecutionSnapshot, TaskDetail, TaskSummary } from '../types'

const demoProject: ProjectDetail = { id: 'demo-project', name: 'AgentForge', description: 'Local Agent operations workspace.', workspace_root: 'D:/AgentProjects/AgentForge', environment: 'development', status: 'ACTIVE', allowed_capability_ids: ['repository_state', 'project_metadata', 'test_verification'], config_version: 1, recent_task_count: 1, created_at: '2026-08-21T14:00:00Z', updated_at: '2026-08-21T14:00:00Z', recent_tasks: [] }
const demoTask: TaskSummary = { id: 'demo-release-v2', project_id: demoProject.id, title: 'Release v2.0 Verification', goal: 'Verify whether Release v2.0 is ready for release.', workspace: 'D:/AgentProjects/AgentForge', status: 'WAITING_APPROVAL', created_at: '2026-08-21T14:18:07Z', updated_at: '2026-08-21T14:32:01Z' }
demoProject.recent_tasks = [demoTask]
const demoSteps: CapabilityPlanStep[] = [
  { step_id: 'step-1', capability_id: 'repository_state' as const, parameters: {} },
  { step_id: 'step-2', capability_id: 'project_metadata' as const, parameters: { relative_path: 'PROJECT_CONTEXT.md' } },
  { step_id: 'step-3', capability_id: 'test_verification' as const, parameters: { profile: 'smoke' } },
]
const resolved = (
  step_id: string,
  capability_id: string,
  resolved_tool_id: string,
  resolved_action: string,
  normalized_parameters: Record<string, string>,
): ResolvedExecutionSnapshot => ({
  task_id: demoTask.id,
  plan_id: 'plan-demo',
  plan_version: 1,
  step_id,
  capability_id,
  resolved_tool_id,
  resolved_action,
  normalized_parameters,
  registry_fingerprint: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
})
const demoResolved = [
  resolved('step-1', 'repository_state', 'git_read', 'status', {}),
  resolved('step-2', 'project_metadata', 'file_read', 'read_metadata', { relative_path: 'PROJECT_CONTEXT.md' }),
  resolved('step-3', 'test_verification', 'test_run', 'run_profile', { profile: 'smoke' }),
]
const demoAuthority = { project_id: demoProject.id, config_version: 1, authority_fingerprint: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789', canonical_workspace_root: 'd:\\agentprojects\\agentforge' }
const demoPlan: Plan = { id: 'plan-demo', version: 1, validation_status: 'VALID', created_at: '2026-08-21T14:22:41Z', plan_json: { schema_version: 2, steps: demoSteps, resolved_steps: demoResolved, project_authority: demoAuthority } }
const demoSnapshot = { schema_version: 2 as const, project_authority: demoAuthority, steps: demoResolved }
const demoApproval: ApprovalQueueItem = { id: 'approval-demo', task_id: demoTask.id, task_title: demoTask.title, plan_id: demoPlan.id, plan_version: 1, decision: 'PENDING', requested_by: 'planner-agent', created_at: '2026-08-21T14:32:01Z', plan_json: demoPlan.plan_json, resolved_snapshot: demoSnapshot }
const demoDetail: TaskDetail = { task: demoTask, plans: [demoPlan], approvals: [{ id: demoApproval.id, plan_id: demoPlan.id, decision: 'PENDING', approver: 'pending', resolved_snapshot: demoSnapshot, created_at: demoApproval.created_at }], executions: [], evidence: [], audit: [{ id: 'audit-1', event_type: 'TASK_CREATED', actor: 'operator', payload_summary: 'Task created', correlation_id: 'corr-1', created_at: demoTask.created_at }, { id: 'audit-2', event_type: 'PLAN_CREATED', actor: 'planner', payload_summary: 'Validated plan version 1', correlation_id: 'corr-2', created_at: '2026-08-21T14:22:41Z' }] }
const demoProvider: ProviderStatus = { provider: 'mock', model: 'deterministic-mock', configured: true, credential_configured: false, connection_status: 'not tested' }

export function useOperations() {
  const [tasks, setTasks] = useState<TaskSummary[]>([demoTask])
  const [projects, setProjects] = useState<ProjectSummary[]>([demoProject])
  const [project, setProject] = useState<ProjectDetail>(demoProject)
  const [approvals, setApprovals] = useState<ApprovalQueueItem[]>([demoApproval])
  const [selectedId, setSelectedId] = useState<string | undefined>()
  const [detail, setDetail] = useState<TaskDetail>(demoDetail)
  const [report, setReport] = useState<Report>({ task: demoTask, readiness: 'PENDING', summary: 'Awaiting human approval before execution.', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 2, execution_count: 0 })
  const [live, setLive] = useState(false)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus>(demoProvider)
  const [testingProvider, setTestingProvider] = useState(false)
  const [agentPlanning, setAgentPlanning] = useState(false)
  const [agentError, setAgentError] = useState<string | null>(null)
  const providerStatusRequestId = useRef(0)
  const [actionError, setActionError] = useState<string | null>(null)

  const refreshTask = useCallback(async (id: string) => {
    const [nextDetail, nextReport, nextApprovals] = await Promise.all([
      api.getTaskDetail(id),
      api.getReport(id),
      api.getPendingApprovals(),
    ])
    setSelectedId(id)
    setDetail(nextDetail)
    setReport(nextReport)
    setApprovals(nextApprovals)
    setLive(true)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [nextTasks, nextApprovals, nextProjects] = await Promise.all([api.listTasks(), api.getPendingApprovals(), api.listProjects()])
      setTasks(nextTasks); setApprovals(nextApprovals); setProjects(nextProjects)
      const id = selectedId && nextTasks.some(task => task.id === selectedId) ? selectedId : nextTasks[0]?.id
      if (id) {
        setSelectedId(id)
        setDetail(await api.getTaskDetail(id))
        setReport(await api.getReport(id))
      }
      setLive(true)
    } catch { setLive(false) }
  }, [selectedId])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const requestId = ++providerStatusRequestId.current
    void api.getProviderStatus().then((status) => {
      if (requestId === providerStatusRequestId.current) setProviderStatus(status)
    }).catch(() => undefined)
  }, [])

  async function testProviderConnection() {
    setTestingProvider(true)
    providerStatusRequestId.current += 1
    try { setProviderStatus(await api.testProviderConnection()) } finally { setTestingProvider(false) }
  }

  async function createAgentTask(projectId: string, goal: string): Promise<TaskSummary> {
    setAgentPlanning(true)
    setAgentError(null)
    try {
      const created = await api.createTask({ project_id: projectId, title: 'Repository Analyst Agent', goal })
      setSelectedId(created.id)
      const plan = await api.createPlan(created.id)
      let authoritativeDetail = await api.getTaskDetail(created.id)
      const matching = authoritativeDetail.approvals.find((item) => item.plan_id === plan.id && item.resolved_snapshot && item.decision !== 'REJECTED')
      if (!matching) {
        try {
          await api.createApproval(created.id, plan.id, plan.version)
        } catch (error) {
          authoritativeDetail = await api.getTaskDetail(created.id)
          const recovered = authoritativeDetail.approvals.some((item) => item.plan_id === plan.id && item.resolved_snapshot && item.decision !== 'REJECTED')
          if (!recovered) throw error
        }
      }
      await refreshTask(created.id)
      return created
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Agent planning failed.'
      setAgentError(message)
      throw error
    } finally {
      setAgentPlanning(false)
    }
  }

  async function chooseTask(id: string) {
    setSelectedId(id)
    try { setDetail(await api.getTaskDetail(id)); setReport(await api.getReport(id)); setLive(true) } catch { if (id === demoTask.id) { setDetail(demoDetail); setReport({ task: demoTask, readiness: 'PENDING', summary: 'Awaiting human approval before execution.', completed_steps: 0, failed_steps: 0, rejected_steps: 0, evidence: [], audit_count: 2, execution_count: 0 }) } }
  }

  async function chooseProject(id: string) {
    try { setProject(await api.getProject(id)); setLive(true) }
    catch { if (id === demoProject.id) setProject(demoProject) }
  }

  async function createProject(payload: { name: string; description?: string; workspace_root: string; environment: string; allowed_capability_ids: string[] }) {
    await api.createProject(payload)
    await refresh()
  }

  async function validateWorkspace(workspace: string) {
    return (await api.validateWorkspace(workspace)).canonical_workspace_root
  }

  async function createTask(projectId: string, title: string, goal: string) {
    await api.createTask({ project_id: projectId, title, goal })
    await chooseProject(projectId)
    await refresh()
  }

  async function archiveProject(projectId: string, version: number) {
    await api.archiveProject(projectId, version)
    await chooseProject(projectId)
    await refresh()
  }

  async function act(action: 'approve' | 'reject' | 'cancel', approvalId?: string) {
    setActionError(null)
    try {
      const item = approvalId ? approvals.find((candidate) => candidate.id === approvalId) : undefined
      let effectiveApprovalId = item?.approval_id ?? (item ? undefined : approvalId)
      if (item && !effectiveApprovalId) {
        const created = await api.createApproval(item.task_id, item.plan_id, item.plan_version)
        effectiveApprovalId = created.id
      }
      if (action === 'approve' && effectiveApprovalId) await api.approve(effectiveApprovalId)
      if (action === 'reject' && effectiveApprovalId) await api.reject(effectiveApprovalId, 'Plan requires operator changes')
      if (action === 'cancel' && selectedId) await api.cancel(selectedId)
      await refresh()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'The decision could not be completed.')
    }
  }

  return { tasks, approvals, projects, project, detail, report, selectedId, chooseTask, chooseProject, createProject, validateWorkspace, createTask, createAgentTask, refreshTask, archiveProject, act, refresh, live, providerStatus, testingProvider, testProviderConnection, actionError, agentPlanning, agentError }
}

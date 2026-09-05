import type { AgentApprovalCommand, ApprovalQueueItem, Approval, Diagnostics, Plan, ProjectDetail, ProjectSummary, ProviderStatus, ReconciliationEligibility, ReconciliationResult, Report, RuntimeResult, TaskDetail, TaskSummary } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed: ${response.status}`)
  return response.json() as Promise<T>
}

function normalizeTaskDetail(detail: TaskDetail): TaskDetail {
  return {
    ...detail,
    approvals: detail.approvals.map((approval) => {
      if (approval.plan_version != null) return approval
      const plan = detail.plans.find(candidate => candidate.id === approval.plan_id)
      return plan ? { ...approval, plan_version: plan.version } : approval
    }),
  }
}

export const api = {
  listProjects: () => request<ProjectSummary[]>('/projects'),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (payload: { name: string; description?: string; workspace_root: string; environment: string; allowed_capability_ids: string[] }) =>
    request<ProjectSummary>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  validateWorkspace: (workspace_root: string) => request<{ valid: true; canonical_workspace_root: string }>('/projects/validate-workspace', { method: 'POST', body: JSON.stringify({ workspace_root }) }),
  archiveProject: (id: string, expected_config_version: number) => request<ProjectSummary>(`/projects/${id}/archive`, { method: 'POST', body: JSON.stringify({ expected_config_version }) }),
  createTask: (payload: { project_id: string; title: string; goal: string }) => request<TaskSummary>('/tasks', { method: 'POST', body: JSON.stringify(payload) }),
  createPlan: (taskId: string, context: Record<string, unknown> = {}) => request<Plan>(`/tasks/${taskId}/plan`, { method: 'POST', body: JSON.stringify({ context }) }),
  createApproval: (taskId: string, planId: string, planVersion: number) => request<Approval>(`/tasks/${taskId}/approval`, { method: 'POST', body: JSON.stringify({ plan_id: planId, plan_version: planVersion, requested_by: 'operator' }) }),
  approveAndExecuteTask: (taskId: string, command: AgentApprovalCommand) => request<RuntimeResult>(`/tasks/${taskId}/approve-and-execute`, { method: 'POST', body: JSON.stringify(command) }),
  executeTask: (taskId: string) => request<TaskSummary>(`/tasks/${taskId}/execute`, { method: 'POST' }),
  listTasks: () => request<TaskSummary[]>('/tasks'),
  getTaskDetail: (id: string) => request<TaskDetail>(`/tasks/${id}/detail`).then(normalizeTaskDetail),
  getPendingApprovals: () => request<ApprovalQueueItem[]>('/approvals/pending'),
  getReport: (id: string) => request<Report>(`/tasks/${id}/report`),
  getReconciliationEligibility: (id: string) => request<ReconciliationEligibility>(`/tasks/${id}/reconciliation`),
  reconcileTask: (id: string) => request<ReconciliationResult>(`/tasks/${id}/reconciliation`, { method: 'POST', body: JSON.stringify({ actor: 'operator' }) }),
  getProviderStatus: () => request<ProviderStatus>('/llm/provider'),
  testProviderConnection: () => request<ProviderStatus>('/llm/provider/test', { method: 'POST' }),
  getDiagnostics: () => request<Diagnostics>('/diagnostics'),
  approve: (id: string) => request(`/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ actor: 'operator' }) }),
  reject: (id: string, reason: string) => request(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ actor: 'operator', reason }) }),
  cancel: (taskId: string) => request(`/tasks/${taskId}/cancel`, { method: 'POST', body: JSON.stringify({ actor: 'operator', reason: 'Cancelled from operations console' }) }),
}

import type { ApprovalQueueItem, ProviderStatus, Report, TaskDetail, TaskSummary } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed: ${response.status}`)
  return response.json() as Promise<T>
}

export const api = {
  listTasks: () => request<TaskSummary[]>('/tasks'),
  getTaskDetail: (id: string) => request<TaskDetail>(`/tasks/${id}/detail`),
  getPendingApprovals: () => request<ApprovalQueueItem[]>('/approvals/pending'),
  getReport: (id: string) => request<Report>(`/tasks/${id}/report`),
  getProviderStatus: () => request<ProviderStatus>('/llm/provider'),
  testProviderConnection: () => request<ProviderStatus>('/llm/provider/test', { method: 'POST' }),
  approve: (id: string) => request(`/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify({ actor: 'operator' }) }),
  reject: (id: string, reason: string) => request(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify({ actor: 'operator', reason }) }),
  cancel: (taskId: string) => request(`/tasks/${taskId}/cancel`, { method: 'POST', body: JSON.stringify({ actor: 'operator', reason: 'Cancelled from operations console' }) }),
}

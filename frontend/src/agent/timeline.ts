import type { ApprovalQueueItem, Report, TaskDetail } from '../types'
import type { AgentTimelineEntry } from './types'

export type AgentTimelineInput = {
  detail: TaskDetail
  report: Report
  pendingApproval?: ApprovalQueueItem
  transientPlanning?: boolean
}

type Draft = AgentTimelineEntry & { order: number }

function versionFrom(text: string, fallback?: number): number | undefined {
  const match = text.match(/version\s+(\d+)/i)
  return match ? Number(match[1]) : fallback
}

export function buildAgentTimeline({ detail, report, pendingApproval, transientPlanning = false }: AgentTimelineInput): AgentTimelineEntry[] {
  const drafts: Draft[] = []
  const add = (entry: Omit<AgentTimelineEntry, 'id'> & { id?: string }, order: number) => drafts.push({ id: entry.id ?? `${entry.kind}-${order}`, order, ...entry })
  add({ kind: 'GOAL_RECEIVED', timestamp: detail.task.created_at, status: 'CREATED', summary: 'Goal received' }, 0)

  if (transientPlanning) add({ kind: 'PLANNING', timestamp: detail.task.updated_at, status: 'PLANNING', summary: 'Planning...' }, 1)

  detail.audit.forEach((event, index) => {
    const kind = event.event_type
    if (kind === 'PLAN_CREATED') add({ id: event.id, kind: 'PLAN_CREATED', timestamp: event.created_at, planVersion: versionFrom(event.payload_summary), status: 'VALID', summary: event.payload_summary }, 10 + index)
    if (kind === 'RUNTIME_OBSERVATION') add({ id: event.id, kind: 'OBSERVATION_RECORDED', timestamp: event.created_at, status: 'RECORDED', summary: event.payload_summary }, 20 + index)
    if (kind === 'REPLAN_REQUESTED') add({ id: event.id, kind: 'REPLANNING', timestamp: event.created_at, status: 'REPLANNING', summary: event.payload_summary }, 30 + index)
    if (kind === 'PLAN_VERSION_CREATED') add({ id: event.id, kind: 'SUCCESSOR_PLAN_CREATED', timestamp: event.created_at, planVersion: versionFrom(event.payload_summary), status: 'VALID', summary: event.payload_summary }, 40 + index)
  })

  detail.approvals.forEach((approval, index) => {
    const status = approval.decision
    if (status === 'PENDING') add({ id: approval.id, kind: 'WAITING_APPROVAL', timestamp: approval.created_at, planVersion: detail.plans.find(plan => plan.id === approval.plan_id)?.version, status, summary: 'Waiting for approval' }, 50 + index)
    if (status === 'APPROVED') add({ id: approval.id, kind: 'APPROVED', timestamp: approval.created_at, planVersion: detail.plans.find(plan => plan.id === approval.plan_id)?.version, status, summary: 'Approval granted' }, 50 + index)
    if (status === 'REJECTED') add({ id: approval.id, kind: 'APPROVAL_REJECTED', timestamp: approval.created_at, planVersion: detail.plans.find(plan => plan.id === approval.plan_id)?.version, status, summary: approval.reason ?? 'Approval rejected' }, 50 + index)
  })

  if (pendingApproval && !detail.approvals.some(approval => approval.id === pendingApproval.approval_id || approval.id === pendingApproval.id)) {
    add({ id: pendingApproval.id, kind: 'WAITING_APPROVAL', timestamp: pendingApproval.created_at, planVersion: pendingApproval.plan_version, status: pendingApproval.decision, summary: 'Waiting for approval' }, 60)
  }

  detail.executions.forEach((execution, index) => add({
    id: execution.id,
    kind: 'TOOL_EXECUTION_COMPLETED',
    timestamp: execution.finished_at ?? execution.started_at,
    status: execution.status,
    summary: `${execution.tool_name} · ${execution.action}: ${execution.result_summary ?? execution.status}`,
    raw: { tool_name: execution.tool_name, action: execution.action, result_summary: execution.result_summary },
  }, 70 + index))

  if (detail.task.status === 'SUCCESS') add({ kind: 'COMPLETED', timestamp: detail.task.updated_at, status: detail.task.status, summary: 'Completed' }, 90)
  if (detail.task.status === 'FAILED' || report.readiness === 'FAIL') add({ kind: 'FAILED', timestamp: detail.task.updated_at, status: detail.task.status, summary: `FAILED: ${report.summary}` }, 90)

  return drafts.sort((left, right) => left.timestamp.localeCompare(right.timestamp) || left.order - right.order || left.id.localeCompare(right.id)).map(({ order: _order, ...entry }) => entry)
}

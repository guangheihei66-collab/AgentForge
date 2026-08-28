import type { ApprovalQueueItem, Report, TaskDetail } from '../types'
import type { AgentTimelineEntry } from './types'

export type AgentTimelineInput = {
  detail: TaskDetail
  report: Report
  pendingApproval?: ApprovalQueueItem
  transientPlanning?: boolean
}

type Draft = AgentTimelineEntry & { order: number }

const IGNORED_AUDIT_EVENTS = new Set([
  'TASK_CREATED',
  'TASK_STATE_CHANGED',
  'APPROVAL_CREATED',
  'TOOL_EXECUTION_COMPLETED',
  'RUNTIME_TRANSITION',
  'LLM_PLAN_REQUESTED',
  'LLM_PLAN_SUCCEEDED',
  'LLM_PLAN_FAILED',
  'CAPABILITY_REQUESTED',
  'CAPABILITY_RESOLVED',
  'APPROVAL_COMMAND_SUCCEEDED',
  'APPROVAL_COMMAND_FAILED',
  'EXECUTION_INITIATION_REQUESTED',
  'EXECUTION_INITIATION_STARTED',
  'EXECUTION_INITIATION_FAILED',
  'ANALYST_SYNTHESIS_REQUESTED',
  'ANALYST_SYNTHESIS_STARTED',
  'ANALYST_SYNTHESIS_SUCCEEDED',
  'ANALYST_SYNTHESIS_FAILED',
])

const HIDDEN_KEYS = /reasoning|chain[_ -]?of[_ -]?thought|system[_ -]?prompt/i

function versionFrom(text: string, fallback?: number): number | undefined {
  const match = text.match(/version\s+(\d+)/i)
  return match ? Number(match[1]) : fallback
}

function parsePayload(text: string): Record<string, unknown> | undefined {
  try {
    const value = JSON.parse(text) as unknown
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : undefined
  } catch {
    return undefined
  }
}

function bounded(value: unknown, limit = 500): unknown {
  if (typeof value === 'string') return value.slice(0, limit)
  if (Array.isArray(value)) return value.slice(0, 8).map(item => bounded(item, 200))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .slice(0, 16)
        .flatMap(([key, item]) => HIDDEN_KEYS.test(key) ? [] : [[key.slice(0, 128), bounded(item, 200)]]),
    )
  }
  return value
}

function technicalPayload(payload: Record<string, unknown>): Record<string, unknown> {
  return bounded(payload) as Record<string, unknown>
}

function textValue(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key]
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, 500) : undefined
}

function observationProjection(payload: Record<string, unknown>): { summary: string; stepId?: string; status: string; raw: Record<string, unknown> } {
  const decision = textValue(payload, 'decision')
  const capability = textValue(payload, 'capability_id')
  const stepId = textValue(payload, 'step_id')
  const status = textValue(payload, 'status') ?? 'RECORDED'
  const resultSummary = textValue(payload, 'result_summary')
  const summaryParts = [
    decision ? `Runtime decision: ${decision}` : 'Observation recorded',
    capability ?? stepId,
    status,
  ].filter(Boolean)
  if (resultSummary) summaryParts.push(resultSummary)
  return {
    summary: summaryParts.join(' · ').slice(0, 800),
    stepId,
    status,
    raw: technicalPayload(payload),
  }
}

export function buildAgentTimeline({ detail, report, pendingApproval, transientPlanning = false }: AgentTimelineInput): AgentTimelineEntry[] {
  const drafts: Draft[] = []
  const add = (entry: Omit<AgentTimelineEntry, 'id'> & { id?: string }, order: number) => drafts.push({ id: entry.id ?? `${entry.kind}-${order}`, order, ...entry })
  add({ kind: 'GOAL_RECEIVED', timestamp: detail.task.created_at, status: 'CREATED', summary: 'Goal received' }, 0)

  if (transientPlanning) add({ kind: 'PLANNING', timestamp: detail.task.updated_at, status: 'PLANNING', summary: 'Planning...' }, 1)

  detail.audit.forEach((event, index) => {
    const kind = event.event_type
    const payload = parsePayload(event.payload_summary)
    if (kind === 'PLAN_CREATED') {
      const planVersion = versionFrom(event.payload_summary)
      add({ id: event.id, kind: 'PLAN_CREATED', timestamp: event.created_at, planVersion, status: 'VALID', summary: planVersion ? `Plan v${planVersion} · VALID` : 'Validated plan' }, 10 + index)
      return
    }
    if (kind === 'RUNTIME_OBSERVATION') {
      const projection = payload ? observationProjection(payload) : { summary: 'Observation recorded', status: 'RECORDED', raw: {} }
      add({ id: event.id, kind: 'OBSERVATION_RECORDED', timestamp: event.created_at, stepId: projection.stepId, status: projection.status, summary: projection.summary, raw: Object.keys(projection.raw).length ? projection.raw : undefined }, 20 + index)
      return
    }
    if (kind === 'REPLAN_REQUESTED') add({ id: event.id, kind: 'REPLANNING', timestamp: event.created_at, status: 'REPLANNING', summary: event.payload_summary.slice(0, 500), raw: payload ? technicalPayload(payload) : undefined }, 30 + index)
    if (kind === 'PLAN_VERSION_CREATED') {
      const planVersion = versionFrom(event.payload_summary)
      add({ id: event.id, kind: 'SUCCESSOR_PLAN_CREATED', timestamp: event.created_at, planVersion, status: 'VALID', summary: planVersion ? `Plan v${planVersion} · VALID` : 'Successor plan created' }, 40 + index)
      return
    }
    if (!IGNORED_AUDIT_EVENTS.has(kind) && kind !== 'PLAN_CREATED' && kind !== 'RUNTIME_OBSERVATION' && kind !== 'REPLAN_REQUESTED' && kind !== 'PLAN_VERSION_CREATED') {
      add({ id: event.id, kind: 'UNKNOWN_EVENT', timestamp: event.created_at, status: 'RECORDED', summary: 'Technical event recorded', raw: payload ? technicalPayload(payload) : undefined }, 45 + index)
    }
  })

  detail.approvals.forEach((approval, index) => {
    const status = approval.decision
    const planVersion = detail.plans.find(plan => plan.id === approval.plan_id)?.version
    if (status === 'PENDING') add({ id: approval.id, kind: 'WAITING_APPROVAL', timestamp: approval.created_at, planVersion, status, summary: planVersion ? `Plan v${planVersion} · awaiting approval` : 'Waiting for approval' }, 50 + index)
    if (status === 'APPROVED') add({ id: approval.id, kind: 'APPROVED', timestamp: approval.created_at, planVersion, status, summary: planVersion ? `Plan v${planVersion} · approved` : 'Approval granted' }, 50 + index)
    if (status === 'REJECTED') add({ id: approval.id, kind: 'APPROVAL_REJECTED', timestamp: approval.created_at, planVersion, status, summary: approval.reason?.slice(0, 500) ?? 'Approval rejected' }, 50 + index)
  })

  if (pendingApproval && !detail.approvals.some(approval => approval.id === pendingApproval.approval_id || approval.id === pendingApproval.id)) {
    add({ id: pendingApproval.id, kind: 'WAITING_APPROVAL', timestamp: pendingApproval.created_at, planVersion: pendingApproval.plan_version, status: pendingApproval.decision, summary: `Plan v${pendingApproval.plan_version} · awaiting approval` }, 60)
  }

  detail.executions.forEach((execution, index) => add({
    id: execution.id,
    kind: 'TOOL_EXECUTION_COMPLETED',
    timestamp: execution.finished_at ?? execution.started_at,
    status: execution.status,
    summary: `${execution.tool_name} · ${execution.action} · ${execution.status}${execution.result_summary ? ` · ${execution.result_summary}` : ''}`.slice(0, 800),
    raw: technicalPayload({ tool_name: execution.tool_name, action: execution.action, status: execution.status, result_summary: execution.result_summary }),
  }, 70 + index))

  if (detail.task.status === 'SUCCESS') add({ kind: 'COMPLETED', timestamp: detail.task.updated_at, status: detail.task.status, summary: 'Completed' }, 90)
  if (detail.task.status === 'FAILED' || report.readiness === 'FAIL') add({ kind: 'FAILED', timestamp: detail.task.updated_at, status: detail.task.status, summary: `FAILED: ${report.summary}`.slice(0, 800) }, 90)

  return drafts.sort((left, right) => left.timestamp.localeCompare(right.timestamp) || left.order - right.order || left.id.localeCompare(right.id)).map(({ order: _order, ...entry }) => entry)
}

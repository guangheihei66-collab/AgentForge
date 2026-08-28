import type { Plan, TaskDetail, TaskSummary } from '../types'
import { isTerminalTaskStatus } from './polling'

const executionStartedEventTypes = new Set([
  'EXECUTION_INITIATION_STARTED',
  'RUNTIME_EXECUTION',
  'RUNTIME_OBSERVATION',
  'RUNTIME_DECISION',
  'TOOL_EXECUTION',
])

export function canResumeApprovedExecution({ task, detail, currentPlan }: { task?: TaskSummary; detail?: TaskDetail; currentPlan?: Plan }): boolean {
  if (!task || !detail || !currentPlan) return false
  if (task.status !== 'RUNNING' || detail.task.status !== 'RUNNING' || isTerminalTaskStatus(task.status)) return false
  if (detail.executions.length > 0) return false
  if (detail.audit.some(event => executionStartedEventTypes.has(event.event_type))) return false
  return detail.approvals.some(approval => approval.decision === 'APPROVED' && approval.plan_id === currentPlan.id && approval.plan_version === currentPlan.version)
}

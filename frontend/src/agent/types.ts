export type AgentTimelineKind =
  | 'GOAL_RECEIVED'
  | 'PLANNING'
  | 'PLAN_CREATED'
  | 'WAITING_APPROVAL'
  | 'APPROVED'
  | 'APPROVAL_REJECTED'
  | 'STEP_STARTED'
  | 'TOOL_EXECUTION_COMPLETED'
  | 'OBSERVATION_RECORDED'
  | 'STEP_FAILED'
  | 'REPLANNING'
  | 'SUCCESSOR_PLAN_CREATED'
  | 'COMPLETED'
  | 'FAILED'
  | 'UNKNOWN_EVENT'

export type AgentTimelineEntry = {
  id: string
  kind: AgentTimelineKind
  timestamp: string
  planVersion?: number
  stepId?: string
  status: string
  summary: string
  raw?: Record<string, unknown>
}

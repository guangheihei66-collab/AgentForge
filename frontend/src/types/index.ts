export type TaskStatus = 'CREATED' | 'PLANNING' | 'WAITING_APPROVAL' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELLED'

export type TaskSummary = {
  id: string
  title: string
  goal: string
  workspace: string
  status: TaskStatus
  created_at: string
  updated_at: string
}

export type PlanStep = {
  step_id: string
  tool: string
  action: string
  risk_level: string
  permission_level: string
}

export type Plan = { id: string; version: number; plan_json: { steps: PlanStep[] }; validation_status: string; created_at: string }
export type Approval = { id: string; plan_id: string; decision: string; approver: string; reason?: string; created_at: string }
export type Execution = { id: string; tool_name: string; action: string; status: string; result_summary?: string; artifact_path?: string; content_hash?: string; started_at: string; finished_at?: string }
export type Evidence = { id: string; summary: string; artifact_path?: string; content_hash?: string; created_at: string }
export type AuditEvent = { id: string; event_type: string; actor: string; payload_summary: string; correlation_id: string; created_at: string }
export type TaskDetail = { task: TaskSummary; plans: Plan[]; approvals: Approval[]; executions: Execution[]; evidence: Evidence[]; audit: AuditEvent[] }
export type ApprovalQueueItem = { id: string; task_id: string; task_title: string; plan_id: string; plan_version: number; decision: string; requested_by: string; created_at: string; plan_json: { steps: PlanStep[] } }
export type Report = { task: TaskSummary; readiness: 'PASS' | 'FAIL' | 'PENDING'; summary: string; completed_steps: number; failed_steps: number; evidence: Evidence[]; audit_count: number; execution_count: number }

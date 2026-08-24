export type TaskStatus = 'CREATED' | 'PLANNING' | 'WAITING_APPROVAL' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELLED'

export type TaskSummary = {
  id: string
  project_id: string | null
  title: string
  goal: string
  workspace: string
  status: TaskStatus
  created_at: string
  updated_at: string
}

export type CapabilityPlanStep = {
  step_id: string
  capability_id: 'repository_state' | 'project_metadata' | 'test_verification'
  parameters: Record<string, string>
}

export type ResolvedExecutionSnapshot = {
  task_id: string
  plan_id: string
  plan_version: number
  step_id: string
  capability_id: string
  resolved_tool_id: string
  resolved_action: string
  normalized_parameters: Record<string, string>
  registry_fingerprint: string
}

export type PlanDocument = {
  schema_version: 2
  summary?: string
  steps: CapabilityPlanStep[]
  resolved_steps: ResolvedExecutionSnapshot[]
  project_authority: ProjectAuthority
}

export type ProjectAuthority = {
  project_id: string
  config_version: number
  authority_fingerprint: string
  canonical_workspace_root: string
}

export type ProjectStatus = 'ACTIVE' | 'ARCHIVED'
export type ProjectSummary = {
  id: string
  name: string
  description?: string | null
  workspace_root: string
  environment: string
  status: ProjectStatus
  allowed_capability_ids: string[]
  config_version: number
  recent_task_count: number
  created_at: string
  updated_at: string
}
export type ProjectTask = Pick<TaskSummary, 'id' | 'title' | 'goal' | 'status' | 'created_at'>
export type ProjectDetail = ProjectSummary & { recent_tasks: ProjectTask[] }

export type ProviderStatus = {
  provider: string
  model: string
  configured: boolean
  credential_configured: boolean
  connection_status: 'not tested' | 'success' | 'failed'
  failure_category?: string | null
}

export type ApprovalSnapshot = {
  schema_version: 2
  project_authority: ProjectAuthority
  steps: ResolvedExecutionSnapshot[]
}

export type Plan = { id: string; version: number; plan_json: PlanDocument; validation_status: string; created_at: string }
export type Approval = { id: string; plan_id: string; decision: string; approver: string; reason?: string; resolved_snapshot?: ApprovalSnapshot; created_at: string }
export type Execution = { id: string; tool_name: string; action: string; status: string; result_summary?: string; artifact_path?: string; content_hash?: string; started_at: string; finished_at?: string }
export type Evidence = { id: string; summary: string; artifact_path?: string; content_hash?: string; created_at: string }
export type AuditEvent = { id: string; event_type: string; actor: string; payload_summary: string; correlation_id: string; created_at: string }
export type TaskDetail = { task: TaskSummary; plans: Plan[]; approvals: Approval[]; executions: Execution[]; evidence: Evidence[]; audit: AuditEvent[] }
export type ApprovalQueueItem = { id: string; approval_id?: string | null; task_id: string; task_title: string; plan_id: string; plan_version: number; decision: string; requested_by: string; created_at: string; plan_json: PlanDocument; resolved_snapshot: ApprovalSnapshot }
export type Report = { task: TaskSummary; readiness: 'PASS' | 'FAIL' | 'PENDING'; summary: string; completed_steps: number; failed_steps: number; evidence: Evidence[]; audit_count: number; execution_count: number }

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
  analysis_profile?: string | null
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
export type HealthState = 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY' | 'UNKNOWN'
export type ExecutionInitiationState = 'NOT_REQUESTED' | 'REQUESTED' | 'STARTED' | 'FAILED'
export type CommandProvenance = {
  command_kind: string
  task_id: string
  task_state: string
  plan_id: string | null
  plan_version: number | null
  approval_id: string | null
  approval_state: string | null
  authority_validation: string | null
  approval_persistence: string | null
  execution_initiation: ExecutionInitiationState
  last_checkpoint: string
  correlation_id: string
  failure_category: string | null
}
export type Diagnostics = {
  identity: { product: string; version: string; revision: string | null; environment: string }
  health: { overall: HealthState; backend: HealthState; database: HealthState; provider: HealthState }
  provider: { provider: string; model: string; structured_output_mode: string; credential_configured: boolean; configuration?: 'CONFIGURED' | 'NOT_CONFIGURED' | 'UNKNOWN'; connection: string }
  recent_task: { id: string; state: string; plan_version: number | null; approval: string | null; executions: { total: number; success: number; failed: number; rejected: number }; evidence_count: number; observation_count: number; replan_count: number } | null
  planner_provider?: string | null
  planner_model?: string | null
  analyst_provider?: string | null
  analyst_model?: string | null
  analyst_synthesis_mode?: AnalystSynthesisMode
  analyst?: { status: AnalystSynthesisStatus; synthesis_mode?: AnalystSynthesisMode; provider?: string | null; model?: string | null }
  command_provenance: CommandProvenance | null
  recent_errors: string[]
}

export type ApprovalSnapshot = {
  schema_version: 2
  project_authority: ProjectAuthority
  steps: ResolvedExecutionSnapshot[]
}

export type Plan = { id: string; version: number; plan_json: PlanDocument; validation_status: string; created_at: string }
export type Approval = { id: string; plan_id: string; plan_version?: number; decision: string; approver: string; reason?: string; resolved_snapshot?: ApprovalSnapshot; created_at: string }
export type Execution = { id: string; tool_name: string; action: string; status: string; result_summary?: string; artifact_path?: string; content_hash?: string; started_at: string; finished_at?: string }
export type Evidence = { id: string; summary: string; artifact_path?: string; content_hash?: string; created_at: string }
export type AuditEvent = { id: string; event_type: string; actor: string; payload_summary: string; correlation_id: string; created_at: string }
export type TaskDetail = { task: TaskSummary; plans: Plan[]; approvals: Approval[]; executions: Execution[]; evidence: Evidence[]; audit: AuditEvent[] }

export type ReconciliationEligibility = { task_id: string; eligible: boolean; reason_code: string }
export type ReconciliationResult = ReconciliationEligibility & { previous_state: string; final_state: string; reconciled: boolean }
export type ApprovalQueueItem = { id: string; approval_id?: string | null; task_id: string; task_title: string; plan_id: string; plan_version: number; decision: string; requested_by: string; created_at: string; plan_json: PlanDocument; resolved_snapshot: ApprovalSnapshot | null }
export type AnalystOutputLanguage = 'en-US' | 'zh-CN'
export type AgentApprovalCommand = { approval_id: string; plan_id: string; plan_version: number; actor: string; language?: AnalystOutputLanguage }
export type RuntimeResult = { task_id: string; plan_id: string; plan_version: number; state: string; decision: string; completed_steps: number; observations: unknown[]; successor_plan_id?: string | null; successor_plan_version?: number | null; approval_id?: string | null }
export type AnalystSynthesisStatus = 'NOT_REQUESTED' | 'PENDING' | 'GENERATING' | 'SUCCEEDED' | 'FAILED'
export type AnalystSynthesisMode = 'REAL' | 'MOCK' | 'FAILED' | 'NOT_REQUESTED' | 'NOT_CONFIGURED'
export type AnalystEvidenceSufficiency = 'SUFFICIENT' | 'PARTIAL' | 'INSUFFICIENT'
export type AnalystSeverity = 'BLOCKER' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
export type AnalystOverallStatus = 'HEALTHY' | 'AT_RISK' | 'BLOCKED' | 'UNKNOWN'
export type AnalystReleaseRecommendation = 'READY' | 'READY_WITH_CONDITIONS' | 'NOT_READY' | 'INSUFFICIENT_EVIDENCE'
export type AnalystFinding = { id: string; title: string; severity: AnalystSeverity; category: string; statement: string; rationale: string; evidence_refs: string[]; recommended_action: string }
export type AnalystNextAction = { priority: number; action: string; rationale: string; evidence_refs: string[] }
export type AnalystReportDocument = { schema_version: 1; task_id: string; plan_id: string; plan_version: number; provider: string; model: string; generated_at: string; language?: AnalystOutputLanguage; summary: string; overall_status: AnalystOverallStatus; release_recommendation: AnalystReleaseRecommendation; findings: AnalystFinding[]; next_actions: AnalystNextAction[]; limitations: string[]; evidence_coverage: { available_count: number; referenced_count: number; truncated: boolean; sufficiency?: AnalystEvidenceSufficiency; notes: string[] } }
export type AnalystSynthesis = { status: AnalystSynthesisStatus; report: AnalystReportDocument | null; failure_category: string | null; provider: string | null; model: string | null; plan_id: string | null; plan_version: number | null; artifact_path: string | null; content_hash: string | null; generated_at: string | null }
export type Report = { task: TaskSummary; readiness: 'PASS' | 'FAIL' | 'PENDING'; summary: string; completed_steps: number; failed_steps: number; rejected_steps: number; evidence: Evidence[]; audit_count: number; execution_count: number; analyst?: AnalystSynthesis }

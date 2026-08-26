import { describe, expect, it } from 'vitest'
import type { ApprovalQueueItem, Report, TaskDetail } from '../types'
import { buildAgentTimeline } from './timeline'

const task = { id: 'task-1', project_id: 'project-1', title: 'Release review', goal: 'Check release risks', workspace: 'D:\\repo', status: 'FAILED' as const, created_at: '2026-08-26T10:00:00Z', updated_at: '2026-08-26T10:06:00Z' }
const plan = (id: string, version: number) => ({ id, version, validation_status: 'VALID', created_at: `2026-08-26T10:0${version}:00Z`, plan_json: { schema_version: 2 as const, summary: `Plan ${version}`, steps: [], resolved_steps: [], project_authority: { project_id: 'project-1', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'd:\\repo' } } })
const detail: TaskDetail = {
  task,
  plans: [plan('plan-2', 2), plan('plan-1', 1)],
  approvals: [{ id: 'approval-2', plan_id: 'plan-2', decision: 'PENDING', approver: 'pending', resolved_snapshot: {}, created_at: '2026-08-26T10:04:30Z' }],
  executions: [{ id: 'execution-1', tool_name: 'test_run', action: 'run_profile', status: 'FAILED', result_summary: 'semantic failure', started_at: '2026-08-26T10:03:00Z', finished_at: '2026-08-26T10:03:10Z' }],
  evidence: [{ id: 'evidence-1', summary: 'test evidence', artifact_path: 'D:\\repo\\result.json', content_hash: 'sha', created_at: '2026-08-26T10:03:11Z' }],
  audit: [
    { id: 'audit-created', event_type: 'TASK_CREATED', actor: 'user', payload_summary: 'Task created', correlation_id: 'c1', created_at: '2026-08-26T10:00:00Z' },
    { id: 'audit-plan', event_type: 'PLAN_CREATED', actor: 'planner', payload_summary: 'Validated plan version 1', correlation_id: 'c2', created_at: '2026-08-26T10:01:00Z' },
    { id: 'audit-observation', event_type: 'RUNTIME_OBSERVATION', actor: 'runtime', payload_summary: 'Observation recorded', correlation_id: 'c3', created_at: '2026-08-26T10:03:12Z' },
    { id: 'audit-replan', event_type: 'REPLAN_REQUESTED', actor: 'runtime', payload_summary: 'Failure requires replanning', correlation_id: 'c4', created_at: '2026-08-26T10:03:20Z' },
    { id: 'audit-successor', event_type: 'PLAN_VERSION_CREATED', actor: 'replanning_service', payload_summary: 'Plan version 2', correlation_id: 'c5', created_at: '2026-08-26T10:04:00Z' },
  ],
}
const report: Report = { task, readiness: 'FAIL', summary: '1 failed', completed_steps: 0, failed_steps: 1, rejected_steps: 0, evidence: detail.evidence, audit_count: detail.audit.length, execution_count: 1 }

describe('authoritative Agent timeline projection', () => {
  it('projects persisted lifecycle facts without inventing success or approval', () => {
    const entries = buildAgentTimeline({ detail, report, pendingApproval: undefined })
    expect(entries.map(entry => entry.kind)).toEqual([
      'GOAL_RECEIVED', 'PLAN_CREATED', 'TOOL_EXECUTION_COMPLETED', 'OBSERVATION_RECORDED',
      'REPLANNING', 'SUCCESSOR_PLAN_CREATED', 'WAITING_APPROVAL', 'FAILED',
    ])
    expect(entries.find(entry => entry.kind === 'TOOL_EXECUTION_COMPLETED')?.status).toBe('FAILED')
    expect(entries.find(entry => entry.kind === 'WAITING_APPROVAL')?.planVersion).toBe(2)
    expect(entries.find(entry => entry.kind === 'FAILED')?.summary).toContain('FAILED')
  })

  it('uses transient Planning only when explicitly supplied and excludes hidden reasoning', () => {
    const entries = buildAgentTimeline({ detail: { ...detail, task: { ...task, status: 'PLANNING' }, plans: [], approvals: [], executions: [], audit: [] }, report: { ...report, readiness: 'PENDING' }, transientPlanning: true })
    expect(entries.map(entry => entry.kind)).toEqual(['GOAL_RECEIVED', 'PLANNING'])
    expect(JSON.stringify(entries)).not.toContain('thinking')
    expect(JSON.stringify(entries)).not.toContain('reasoning')
  })

  it('maps an authoritative approved Approval and terminal success', () => {
    const approved = { ...detail, task: { ...task, status: 'SUCCESS' as const }, approvals: [{ id: 'approval-1', plan_id: 'plan-1', decision: 'APPROVED', approver: 'operator', resolved_snapshot: {}, created_at: '2026-08-26T10:02:00Z' }], executions: [] }
    const entries = buildAgentTimeline({ detail: approved, report: { ...report, task: approved.task, readiness: 'PASS', failed_steps: 0, execution_count: 0 } })
    expect(entries.map(entry => entry.kind)).toContain('APPROVED')
    expect(entries.map(entry => entry.kind)).toContain('COMPLETED')
  })
})

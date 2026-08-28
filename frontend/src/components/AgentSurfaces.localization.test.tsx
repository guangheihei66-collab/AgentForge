import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setI18n } from 'react-i18next'
import { I18nProvider, i18n } from '../i18n'
import { AgentApprovalCard } from './AgentApprovalCard'
import { AgentTimeline } from './AgentTimeline'
import { AgentReportCard } from './AgentReportCard'
import type { ApprovalQueueItem, TaskDetail } from '../types'

const authority = { project_id: 'project-raw', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/AgentForge' }
const item: ApprovalQueueItem = {
  id: 'approval-raw', approval_id: 'approval-raw', task_id: 'task-raw', task_title: 'RAW TASK TITLE', plan_id: 'plan-raw', plan_version: 1, decision: 'PENDING', requested_by: 'planner', created_at: '',
  plan_json: { schema_version: 2, summary: 'RAW PLAN SUMMARY', steps: [{ step_id: 'step-1', capability_id: 'repository_state', parameters: {} }], resolved_steps: [], project_authority: authority },
  resolved_snapshot: { schema_version: 2, project_authority: authority, steps: [] },
}
const detail: TaskDetail = { task: { id: 'task-raw', project_id: 'project-raw', title: 'RAW TASK TITLE', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'FAILED', created_at: '', updated_at: '' }, plans: [], approvals: [], executions: [], evidence: [{ id: 'evidence-raw', summary: 'RAW EVIDENCE', artifact_path: 'artifacts/raw.json', created_at: '' }], audit: [] }

afterEach(async () => { cleanup(); setI18n(i18n); await i18n.changeLanguage('en-US') })

describe('Agent surface localization', () => {
  it('localizes governed approval copy while retaining capability IDs and workspace values', async () => {
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    await localized.changeLanguage('zh-CN')
    render(<I18nProvider i18n={localized}><AgentApprovalCard item={item} onApprove={vi.fn()} onReject={vi.fn()} /></I18nProvider>)
    expect(screen.getByText('需要审批')).toBeInTheDocument()
    expect(screen.getByText('读取仓库状态')).toBeInTheDocument()
    expect(screen.getByText('repository_state')).toBeInTheDocument()
    expect(screen.getByText(/D:\/AgentForge/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '批准并执行' })).toBeInTheDocument()
  })

  it('localizes timeline and report chrome without translating persisted summaries', async () => {
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    await localized.changeLanguage('zh-CN')
    render(<I18nProvider i18n={localized}><><AgentTimeline entries={[{ id: 'goal', kind: 'GOAL_RECEIVED', timestamp: '2026-08-28T10:00:00Z', status: 'CREATED', summary: 'RAW SUMMARY' }]} /><AgentReportCard report={{ task: detail.task, readiness: 'FAIL', summary: 'RAW REPORT', completed_steps: 0, failed_steps: 1, rejected_steps: 0, evidence: [], audit_count: 1, execution_count: 1 }} detail={detail} /></></I18nProvider>)
    expect(screen.getByText('Agent 时间线')).toBeInTheDocument()
    expect(screen.getByText('已收到目标')).toBeInTheDocument()
    expect(screen.getByText('RAW SUMMARY')).toBeInTheDocument()
    expect(screen.getByText('证据支持的报告')).toBeInTheDocument()
    expect(screen.getByText('RAW REPORT')).toBeInTheDocument()
    expect(screen.getByText(/RAW EVIDENCE/)).toBeInTheDocument()
  })
})

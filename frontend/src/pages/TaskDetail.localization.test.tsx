import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { setI18n } from 'react-i18next'
import { I18nProvider, i18n } from '../i18n'
import { TaskDetail } from './TaskDetail'

const authority = { project_id: 'project-raw', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/AgentForge' }
const detail = {
  task: { id: 'task-raw', project_id: 'project-raw', title: 'RAW TASK TITLE', goal: 'RAW GOAL', workspace: 'D:/AgentForge', status: 'SUCCESS' as const, created_at: '2026-08-28T10:00:00Z', updated_at: '2026-08-28T10:00:00Z' },
  plans: [{ id: 'plan-raw', version: 1, validation_status: 'VALID', created_at: '2026-08-28T10:00:00Z', plan_json: { schema_version: 2 as const, summary: 'RAW PLAN SUMMARY', steps: [], resolved_steps: [{ task_id: 'task-raw', plan_id: 'plan-raw', plan_version: 1, step_id: 'step-1', capability_id: 'repository_state', resolved_tool_id: 'git_read', resolved_action: 'status', normalized_parameters: {}, registry_fingerprint: 'fingerprint' }], project_authority: authority } }],
  approvals: [], executions: [], evidence: [{ id: 'evidence-raw', summary: 'RAW EVIDENCE', artifact_path: 'artifacts/raw.json', content_hash: 'hash', created_at: '2026-08-28T10:00:00Z' }], audit: [],
}

afterEach(async () => { cleanup(); setI18n(i18n); await i18n.changeLanguage('en-US') })

describe('Task detail localization', () => {
  it('localizes labels while preserving task, plan, tool, and evidence values', async () => {
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    await localized.changeLanguage('zh-CN')
    render(<I18nProvider i18n={localized}><TaskDetail detail={detail} onBack={() => undefined} onReport={() => undefined} /></I18nProvider>)

    expect(screen.getByText('任务详情')).toBeInTheDocument()
    expect(screen.getByText('RAW TASK TITLE')).toBeInTheDocument()
    expect(screen.getByText('RAW GOAL')).toBeInTheDocument()
    expect(screen.getByText(/git_read/)).toBeInTheDocument()
    expect(screen.getByText('RAW EVIDENCE')).toBeInTheDocument()
    expect(screen.getByText('artifacts/raw.json')).toBeInTheDocument()
  })
})

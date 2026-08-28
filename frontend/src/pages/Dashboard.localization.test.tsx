import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { setI18n } from 'react-i18next'
import { I18nProvider, i18n } from '../i18n'
import { Dashboard } from './Dashboard'

const task = {
  id: 'task-raw', project_id: 'project-raw', title: 'RAW TASK TITLE', goal: 'RAW GOAL', workspace: 'D:/AgentForge',
  status: 'WAITING_APPROVAL' as const, created_at: '2026-08-28T10:00:00Z', updated_at: '2026-08-28T10:00:00Z',
}

const approval = {
  id: 'approval-raw', task_id: task.id, task_title: task.title, plan_id: 'plan-raw', plan_version: 2,
  decision: 'PENDING', requested_by: 'planner-agent', created_at: '2026-08-28T10:00:00Z',
  plan_json: { schema_version: 2 as const, steps: [], resolved_steps: [], project_authority: { project_id: 'project-raw', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/AgentForge' } },
  resolved_snapshot: null,
}

afterEach(async () => { cleanup(); setI18n(i18n); await i18n.changeLanguage('en-US') })

describe('Dashboard localization', () => {
  it('localizes provider and tracked-count copy while preserving raw task and model values', async () => {
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    await localized.changeLanguage('zh-CN')
    render(<I18nProvider i18n={localized}><Dashboard tasks={[task]} approvals={[approval]} providerStatus={{ provider: 'openai-compatible', model: 'raw-model-v1', configured: true, credential_configured: false, connection_status: 'success' }} testingProvider={false} onTestProvider={() => undefined} onTask={() => undefined} onApprovals={() => undefined} /></I18nProvider>)

    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('OpenAI 兼容')).toBeInTheDocument()
    expect(screen.getByText('已跟踪 1 项')).toBeInTheDocument()
    expect(screen.getAllByText('RAW TASK TITLE').length).toBeGreaterThan(0)
    expect(screen.getByText('raw-model-v1')).toBeInTheDocument()
  })
})

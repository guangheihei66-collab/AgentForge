import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { I18nProvider, i18n } from '../i18n'
import { TaskDetail } from './TaskDetail'

const detail = {
  task: { id: 'task-1', project_id: 'project-1', title: 'Historical task', goal: 'g', workspace: 'D:/repo', status: 'RUNNING' as const, created_at: '2026-08-29T00:00:00Z', updated_at: '2026-08-29T00:00:00Z' },
  plans: [], approvals: [], executions: [], evidence: [], audit: [],
}

it.each([
  ['en-US', 'Historical failed task detected', 'Reconcile task state'],
  ['zh-CN', '检测到历史失败任务状态', '修复历史任务状态'],
])('shows the server-authorized action in %s', async (locale, warning, action) => {
  const localized = i18n.cloneInstance({ lng: locale })
  await localized.changeLanguage(locale)
  const reconcile = vi.fn()
  render(<I18nProvider i18n={localized}><TaskDetail detail={detail} reconciliation={{ task_id: 'task-1', eligible: true, reason_code: 'ELIGIBLE_HISTORICAL_RUNTIME_FAILURE' }} onReconcile={reconcile} onBack={vi.fn()} onReport={vi.fn()} /></I18nProvider>)
  expect(screen.getByText(warning)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: action }))
  expect(reconcile).toHaveBeenCalledOnce()
})

it('does not offer reconciliation when the server refuses eligibility', () => {
  render(<TaskDetail detail={detail} reconciliation={{ task_id: 'task-1', eligible: false, reason_code: 'NO_TERMINAL_FAILURE_EVIDENCE' }} onReconcile={vi.fn()} onBack={vi.fn()} onReport={vi.fn()} />)
  expect(screen.queryByRole('button', { name: /reconcile task state/i })).not.toBeInTheDocument()
})

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AnalystReportCard } from './AnalystReportCard'
import type { AnalystSynthesis } from '../types'
import { i18n } from '../i18n'

const success: AnalystSynthesis = {
  status: 'SUCCEEDED',
  failure_category: null,
  provider: 'mock',
  model: 'deterministic-mock',
  plan_id: 'plan-1',
  plan_version: 1,
  artifact_path: 'D:/AgentProjectData/AgentForge/artifacts/report.json',
  content_hash: 'abc123',
  generated_at: '2026-08-28T12:00:00Z',
  report: {
    schema_version: 1,
    task_id: 'task-1',
    plan_id: 'plan-1',
    plan_version: 1,
    provider: 'mock',
    model: 'deterministic-mock',
    generated_at: '2026-08-28T12:00:00Z',
    summary: 'Evidence-backed release assessment.',
    overall_status: 'AT_RISK',
    release_recommendation: 'READY_WITH_CONDITIONS',
    findings: [{
      id: 'finding-1',
      title: 'Review test coverage',
      severity: 'MEDIUM',
      category: 'quality',
      statement: 'The evidence supports a conditional release.',
      rationale: 'One check needs human confirmation.',
      evidence_refs: ['evidence-1'],
      recommended_action: 'Confirm the remaining check.',
    }],
    next_actions: [{
      priority: 1,
      action: 'Confirm the remaining check.',
      rationale: 'It is the highest priority follow-up.',
      evidence_refs: ['evidence-1'],
    }],
    limitations: ['External deployment checks were not included.'],
    evidence_coverage: { available_count: 1, referenced_count: 1, truncated: false, sufficiency: 'PARTIAL', notes: [] },
  },
}

describe('Analyst report', () => {
  afterEach(async () => {
    cleanup()
    await i18n.changeLanguage('en-US')
  })

  it('renders evidence-grounded findings, recommendation, actions, and limitations', () => {
    render(<AnalystReportCard analyst={success} />)

    expect(screen.getByText('Evidence-backed release assessment.')).toBeInTheDocument()
    expect(screen.getByText('READY WITH CONDITIONS')).toBeInTheDocument()
    expect(screen.getByText('Review test coverage')).toBeInTheDocument()
    expect(screen.getAllByText('evidence-1')).toHaveLength(2)
    expect(screen.getAllByText('Confirm the remaining check.')).toHaveLength(2)
    expect(screen.getByText('External deployment checks were not included.')).toBeInTheDocument()
  })

  it('does not pretend a report exists for failed or not-requested synthesis', () => {
    const { rerender } = render(
      <AnalystReportCard analyst={{ ...success, status: 'FAILED', report: null, failure_category: 'TIMEOUT' }} />,
    )

    expect(screen.getByText(/governed execution evidence remains available/i)).toBeInTheDocument()
    expect(screen.queryByText('Evidence-backed release assessment.')).not.toBeInTheDocument()

    rerender(<AnalystReportCard analyst={undefined} />)
    expect(screen.getAllByText(/analysis was not requested/i)).toHaveLength(2)
  })

  it('shows an explicit generating state without raw provider content', () => {
    render(<AnalystReportCard analyst={{ ...success, status: 'GENERATING', report: null }} />)

    expect(screen.getAllByText(/analysis is being generated/i)).toHaveLength(2)
    expect(screen.queryByText('deterministic-mock')).not.toBeInTheDocument()
  })

  it('renders evidence sufficiency as an explicit analyst state', () => {
    render(<AnalystReportCard analyst={success} />)

    expect(screen.getByTestId('analyst-evidence-sufficiency')).toHaveTextContent('Partial evidence')
  })

  it('localizes analyst labels and enum copy while preserving evidence identifiers', async () => {
    await i18n.changeLanguage('zh-CN')
    render(<AnalystReportCard analyst={success} />)

    expect(screen.getByText('AI 项目分析')).toBeInTheDocument()
    expect(screen.getByText('整体评估')).toBeInTheDocument()
    expect(screen.getByText('发布建议')).toBeInTheDocument()
    expect(screen.getByText('关键发现')).toBeInTheDocument()
    expect(screen.getByText('判断依据')).toBeInTheDocument()
    expect(screen.getByText('证据引用')).toBeInTheDocument()
    expect(screen.getByText('建议操作')).toBeInTheDocument()
    expect(screen.getByText('下一步行动')).toBeInTheDocument()
    expect(screen.getByText('限制与未知项')).toBeInTheDocument()
    expect(screen.getByText('有条件可以发布')).toBeInTheDocument()
    expect(screen.getByText('中')).toBeInTheDocument()
    expect(screen.getByTestId('analyst-evidence-sufficiency')).toHaveTextContent('部分证据')
    expect(screen.getAllByText('evidence-1')).toHaveLength(2)
  })
})

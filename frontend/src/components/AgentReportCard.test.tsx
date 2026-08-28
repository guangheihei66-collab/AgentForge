import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AgentReportCard } from './AgentReportCard'

describe('Agent report', () => {
  it('presents persisted evidence and failure truthfully', () => {
    render(<AgentReportCard report={{ task: { id: 't', project_id: 'p', title: 'x', goal: 'g', workspace: 'D:/repo', status: 'FAILED', created_at: '', updated_at: '' }, readiness: 'FAIL', summary: 'RAW FAILURE', completed_steps: 0, failed_steps: 1, rejected_steps: 0, evidence: [], audit_count: 1, execution_count: 1 }} detail={{ task: { id: 't', project_id: 'p', title: 'x', goal: 'g', workspace: 'D:/repo', status: 'FAILED', created_at: '', updated_at: '' }, plans: [], approvals: [], executions: [], evidence: [{ id: 'e', summary: 'RAW EVIDENCE', artifact_path: 'src/raw.py', content_hash: 'abc123', created_at: '' }], audit: [] }} />)
    expect(screen.getByText('RAW FAILURE')).toBeInTheDocument()
    expect(screen.getByText(/RAW EVIDENCE/)).toBeInTheDocument()
    expect(screen.getByText(/src\/raw.py/)).toBeInTheDocument()
  })
})

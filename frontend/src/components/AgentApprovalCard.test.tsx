import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentApprovalCard } from './AgentApprovalCard'

const item = { id: 'task-1', approval_id: 'approval-1', task_id: 'task-1', task_title: 'Release review', plan_id: 'plan-1', plan_version: 1, decision: 'PENDING', requested_by: 'planner', created_at: '2026-08-26T10:00:00Z', plan_json: { schema_version: 2 as const, summary: 'Inspect repository', steps: [{ step_id: 'step-1', capability_id: 'repository_state' as const, parameters: {} }], resolved_steps: [], project_authority: { project_id: 'project-1', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/repo' } }, resolved_snapshot: { schema_version: 2 as const, project_authority: { project_id: 'project-1', config_version: 1, authority_fingerprint: 'authority', canonical_workspace_root: 'D:/repo' }, steps: [] } }

describe('Agent approval card', () => {
  afterEach(() => cleanup())
  it('renders authoritative plan scope and friendly capability copy', () => {
    render(<AgentApprovalCard item={item} onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText('Read repository status')).toBeInTheDocument()
    expect(screen.getByText('repository_state')).toBeInTheDocument()
    expect(screen.getByText(/Workspace: D:\/repo/)).toBeInTheDocument()
    expect(screen.getByText(/Arbitrary shell execution is not granted/)).toBeInTheDocument()
  })

  it('uses the authoritative Approval ID for explicit actions', () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    const onReject = vi.fn().mockResolvedValue(undefined)
    render(<AgentApprovalCard item={item} onApprove={onApprove} onReject={onReject} />)
    screen.getByRole('button', { name: 'Approve' }).click()
    expect(onApprove).toHaveBeenCalledWith(item)
  })
})

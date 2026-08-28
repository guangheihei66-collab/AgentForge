import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Approvals } from './Approvals'
import type { ApprovalQueueItem, ApprovalSnapshot, ProjectAuthority } from '../types'

const authority: ProjectAuthority = {
  project_id: 'project-1',
  config_version: 1,
  authority_fingerprint: 'fingerprint',
  canonical_workspace_root: 'D:/AgentForge',
}

const snapshot: ApprovalSnapshot = {
  schema_version: 2,
  project_authority: authority,
  steps: [],
}

const approval: ApprovalQueueItem = {
  id: 'approval-1',
  approval_id: 'approval-1',
  task_id: 'task-1',
  task_title: 'Release Verification',
  plan_id: 'plan-1',
  plan_version: 1,
  decision: 'PENDING',
  requested_by: 'planner-agent',
  created_at: '',
  plan_json: {
    schema_version: 2,
    steps: [],
    resolved_steps: [],
    project_authority: authority,
  },
  resolved_snapshot: snapshot,
}

const renderApprovals = (overrides: Partial<React.ComponentProps<typeof Approvals>> = {}) => render(
  <Approvals
    approvals={[approval]}
    onApprove={vi.fn()}
    onReject={vi.fn()}
    onCancel={vi.fn()}
    onOpenInAgentWorkspace={vi.fn()}
    {...overrides}
  />,
)

describe('Global Approval safety actions', () => {
  afterEach(() => cleanup())

  it('labels the generic approval action as approval-only and explains the execution boundary', () => {
    const onApprove = vi.fn()
    renderApprovals({ onApprove })

    expect(screen.getByRole('button', { name: 'Approve only' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Approve$/ })).not.toBeInTheDocument()
    expect(screen.getByText(/Approving here records the approval only\. It does not start Agent execution\./i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Approve only' }))

    expect(onApprove).toHaveBeenCalledWith(approval.id)
  })

  it('offers a task-scoped Agent Workspace navigation action without approving or executing', () => {
    const onApprove = vi.fn()
    const onReject = vi.fn()
    const onCancel = vi.fn()
    const onOpenInAgentWorkspace = vi.fn()
    renderApprovals({ onApprove, onReject, onCancel, onOpenInAgentWorkspace })

    fireEvent.click(screen.getByRole('button', { name: 'Open in Agent Workspace' }))

    expect(onOpenInAgentWorkspace).toHaveBeenCalledWith(approval.task_id)
    expect(onApprove).not.toHaveBeenCalled()
    expect(onReject).not.toHaveBeenCalled()
    expect(onCancel).not.toHaveBeenCalled()
  })
})

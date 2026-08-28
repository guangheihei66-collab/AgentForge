import { describe, expect, it } from 'vitest'
import { isAgentManagedApproval } from './approval-classification'
import type { ApprovalSnapshot, ProjectAuthority } from '../types'

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

describe('Agent approval classification', () => {
  it('uses the persisted resolved snapshot as the Agent authority', () => {
    expect(isAgentManagedApproval({ resolved_snapshot: snapshot })).toBe(true)
  })

  it('does not infer Agent ownership from descriptive fields', () => {
    expect(isAgentManagedApproval({ resolved_snapshot: null })).toBe(false)
  })
})

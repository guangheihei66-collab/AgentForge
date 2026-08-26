import { describe, expect, it } from 'vitest'
import { capabilityPresentation } from './capabilities'

describe('Repository Analyst capability presentation', () => {
  it('maps governed capability IDs to safe human-facing explanations', () => {
    expect(capabilityPresentation('repository_state')).toEqual({
      label: 'Read repository status',
      description: 'Read-only inspection of the selected repository. No files are modified.',
    })
    expect(capabilityPresentation('project_metadata')).toEqual({
      label: 'Read project metadata',
      description: 'Read only the application-owned metadata allowed for this Project.',
    })
    expect(capabilityPresentation('test_verification')).toEqual({
      label: 'Run project tests',
      description: 'Run a predefined governed test profile; arbitrary shell execution is not granted.',
    })
  })

  it('keeps unknown capability IDs technical', () => {
    expect(capabilityPresentation('future_capability')).toEqual({
      label: 'future_capability',
      description: 'Application-registered capability.',
    })
  })
})

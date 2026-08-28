export type CapabilityPresentation = { label: string; description: string }

const presentations: Record<string, CapabilityPresentation> = {
  repository_state: {
    label: 'Read repository status',
    description: 'Read-only inspection of the selected repository. No files are modified.',
  },
  project_metadata: {
    label: 'Read project metadata',
    description: 'Read only the application-owned metadata allowed for this Project.',
  },
  test_verification: {
    label: 'Run project tests',
    description: 'Run a predefined governed test profile; arbitrary shell execution is not granted.',
  },
}

export function capabilityPresentation(capabilityId: string): CapabilityPresentation {
  return presentations[capabilityId] ?? {
    label: capabilityId,
    description: 'Application-registered capability.',
  }
}

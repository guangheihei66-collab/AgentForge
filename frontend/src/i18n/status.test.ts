import { describe, expect, it } from 'vitest'
import { approvalStatusKey, executionStatusKey, healthStatusKey, providerStatusKey, riskKey, taskStatusKey } from './status'

describe('canonical status presentation mapping', () => {
  it('maps known values and safely falls back without mutating inputs', () => {
    expect(taskStatusKey('WAITING_APPROVAL')).toBe('status.task.waitingApproval')
    expect(taskStatusKey('SUCCESS')).toBe('status.task.success')
    expect(approvalStatusKey('REJECTED')).toBe('status.approval.rejected')
    expect(executionStatusKey('FAILED')).toBe('status.execution.failed')
    expect(providerStatusKey('not tested')).toBe('provider.notTested')
    expect(providerStatusKey('success')).toBe('provider.success')
    expect(healthStatusKey('DEGRADED')).toBe('status.health.degraded')
    expect(riskKey('high')).toBe('status.risk.high')
    expect(taskStatusKey('future-state')).toBe('status.unknown')
  })
})

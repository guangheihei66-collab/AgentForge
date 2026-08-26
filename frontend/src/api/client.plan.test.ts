import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('Agent planning and initial approval API', () => {
  it('creates a real Plan through the existing planning endpoint', async () => {
    const plan = { id: 'plan-1', task_id: 'task-1', version: 1, plan_json: { steps: [] }, validation_status: 'VALID' }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => plan })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.createPlan('task-1', { source: 'agent' })).resolves.toEqual(plan)
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/tasks/task-1/plan', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ context: { source: 'agent' } }),
    }))
  })

  it('creates the initial Approval for the exact returned Plan binding', async () => {
    const approval = { id: 'approval-1', task_id: 'task-1', plan_id: 'plan-1', plan_version: 1, decision: 'PENDING', approver: 'pending', reason: null, resolved_snapshot: {}, created_at: '2026-08-26T10:00:00Z' }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => approval })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.createApproval('task-1', 'plan-1', 1)).resolves.toEqual(approval)
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/tasks/task-1/approval', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ plan_id: 'plan-1', plan_version: 1, requested_by: 'operator' }),
    }))
  })
})

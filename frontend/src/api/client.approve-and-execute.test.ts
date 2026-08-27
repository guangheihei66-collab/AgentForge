import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('Agent approval orchestration API', () => {
  it('sends one exact Agent approve-and-execute command', async () => {
    const result = {
      task_id: 'task-1', plan_id: 'plan-1', plan_version: 1,
      state: 'COMPLETED', decision: 'COMPLETE', completed_steps: 1,
      observations: [], successor_plan_id: null, successor_plan_version: null, approval_id: null,
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => result })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.approveAndExecuteTask('task-1', {
      approval_id: 'approval-1', plan_id: 'plan-1', plan_version: 1, actor: 'operator',
    })).resolves.toEqual(result)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/tasks/task-1/approve-and-execute',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ approval_id: 'approval-1', plan_id: 'plan-1', plan_version: 1, actor: 'operator' }),
      }),
    )
  })
})

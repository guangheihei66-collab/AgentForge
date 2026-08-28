import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { isTerminalTaskStatus, useAgentTaskPolling } from './polling'

afterEach(() => vi.useRealTimers())

describe('Agent task polling', () => {
  it('recognizes only terminal Task states', () => {
    expect(isTerminalTaskStatus('SUCCESS')).toBe(true)
    expect(isTerminalTaskStatus('FAILED')).toBe(true)
    expect(isTerminalTaskStatus('CANCELLED')).toBe(true)
    expect(isTerminalTaskStatus('RUNNING')).toBe(false)
  })

  it('polls active tasks, survives refresh errors, and stops after unmount', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn().mockRejectedValueOnce(new Error('temporary network failure')).mockResolvedValue(undefined)
    const { result, unmount } = renderHook(() => useAgentTaskPolling('task-1', 'RUNNING', refresh, 1000))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(result.current.polling).toBe(true)
    expect(result.current.refreshError).toContain('temporary network failure')
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(refresh).toHaveBeenCalledTimes(2)
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('does not poll terminal tasks', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn()
    renderHook(() => useAgentTaskPolling('task-1', 'SUCCESS', refresh, 1000))
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(refresh).not.toHaveBeenCalled()
  })
})

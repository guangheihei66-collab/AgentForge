import { useEffect, useState } from 'react'

export function isTerminalTaskStatus(status: string): boolean {
  return status === 'SUCCESS' || status === 'FAILED' || status === 'CANCELLED'
}

export function useAgentTaskPolling(taskId: string | undefined, status: string | undefined, refresh: (taskId: string) => Promise<void>, intervalMs = 1500) {
  const [polling, setPolling] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  useEffect(() => {
    if (!taskId || !status || isTerminalTaskStatus(status)) {
      setPolling(false)
      return undefined
    }
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let inFlight = false
    setPolling(true)
    const run = async () => {
      if (disposed || inFlight) return
      inFlight = true
      try {
        await refresh(taskId)
        if (!disposed) setRefreshError(null)
      } catch (error) {
        if (!disposed) setRefreshError(error instanceof Error ? error.message : 'Unable to refresh Agent status')
      } finally {
        inFlight = false
        if (!disposed) timer = setTimeout(() => { void run() }, intervalMs)
      }
    }
    void run()
    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      setPolling(false)
    }
  }, [intervalMs, refresh, status, taskId])

  return { polling, refreshError }
}

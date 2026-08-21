import type { TaskStatus } from '../types'

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status.toLowerCase()}`}>{status.replace('_', ' ')}</span>
}

export function PermissionPill({ value }: { value: string }) {
  return <span className={`permission-pill permission-${value.toLowerCase()}`}>{value.replace('_', ' ')}</span>
}

export function RiskPill({ value }: { value: string }) {
  return <span className={`risk-pill risk-${value.toLowerCase()}`}>{value}</span>
}

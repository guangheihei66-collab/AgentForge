const task: Record<string, string> = { CREATED: 'status.task.created', PLANNING: 'status.task.planning', WAITING_APPROVAL: 'status.task.waitingApproval', RUNNING: 'status.task.running', SUCCESS: 'status.task.success', FAILED: 'status.task.failed', CANCELLED: 'status.task.cancelled' }
const approval: Record<string, string> = { PENDING: 'status.approval.pending', APPROVED: 'status.approval.approved', REJECTED: 'status.approval.rejected', CANCELLED: 'status.approval.cancelled' }
const execution: Record<string, string> = { SUCCESS: 'status.execution.success', FAILED: 'status.execution.failed', REJECTED: 'status.execution.rejected' }
const provider: Record<string, string> = { 'not tested': 'provider.notTested', success: 'provider.success', failed: 'provider.failed' }
const health: Record<string, string> = { HEALTHY: 'status.health.healthy', DEGRADED: 'status.health.degraded', UNHEALTHY: 'status.health.unhealthy', UNKNOWN: 'status.health.unknown' }
const risk: Record<string, string> = { low: 'status.risk.low', medium: 'status.risk.medium', high: 'status.risk.high' }
const permission: Record<string, string> = { SAFE_READ: 'permissions.safeRead', APPROVED_EXEC: 'permissions.approvedExec', DENIED: 'permissions.denied' }
const capability: Record<string, string> = { repository_state: 'capabilities.repository_state', project_metadata: 'capabilities.project_metadata', test_verification: 'capabilities.test_verification' }
const agentStatus: Record<string, string> = { CREATED: 'agent.status.created', PLANNING: 'agent.status.planning', WAITING_APPROVAL: 'agent.status.waitingApproval', RUNNING: 'agent.status.running', SUCCESS: 'agent.status.completed', FAILED: 'agent.status.failed', CANCELLED: 'agent.status.cancelled' }
const map = (values: Record<string, string>, value: string) => values[value] ?? 'status.unknown'
export const taskStatusKey = (value: string) => map(task, value)
export const approvalStatusKey = (value: string) => map(approval, value)
export const executionStatusKey = (value: string) => map(execution, value)
export const providerStatusKey = (value: string) => map(provider, value)
export const healthStatusKey = (value: string) => map(health, value)
export const riskKey = (value: string) => map(risk, value)
export const permissionKey = (value: string) => map(permission, value)
export const capabilityKey = (value: string) => capability[value] ?? 'capabilities.unknown'
export const capabilityLabelKey = (value: string) => `${capabilityKey(value)}.label`
export const capabilityDescriptionKey = (value: string) => `${capabilityKey(value)}.description`
export const agentStatusKey = (value: string) => agentStatus[value] ?? 'agent.status.unknown'

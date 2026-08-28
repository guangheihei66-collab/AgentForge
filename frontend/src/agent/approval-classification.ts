import type { ApprovalQueueItem } from '../types'

/**
 * A resolved snapshot is the persisted authority binding created by the
 * governed Agent planning flow. Do not infer ownership from task copy or
 * project metadata: those fields are descriptive and user-controlled.
 */
export function isAgentManagedApproval(item: Pick<ApprovalQueueItem, 'resolved_snapshot'>): boolean {
  return item.resolved_snapshot !== null && item.resolved_snapshot !== undefined
}

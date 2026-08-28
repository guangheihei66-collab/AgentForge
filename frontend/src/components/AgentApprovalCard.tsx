import { capabilityPresentation } from '../agent/capabilities'
import { useState } from 'react'
import type { ApprovalQueueItem } from '../types'

export function AgentApprovalCard({ item, onApprove, onReject }: { item: ApprovalQueueItem; onApprove: (item: ApprovalQueueItem) => Promise<void>; onReject: (approvalId: string, reason: string) => Promise<void> }) {
  const approvalId = item.approval_id ?? item.id
  const [submitting, setSubmitting] = useState(false)
  async function approve() {
    if (submitting) return
    setSubmitting(true)
    try { await onApprove(item) } finally { setSubmitting(false) }
  }
  return <div className="panel"><div className="panel-title"><h3>Approval required</h3><span>Plan v{item.plan_version}</span></div><p>{item.plan_json.summary ?? 'Review this governed plan before execution.'}</p><p>Workspace: {item.resolved_snapshot?.project_authority?.canonical_workspace_root ?? 'Selected Project workspace'}</p><p>Risk: read-only governed capabilities. Arbitrary shell execution is not granted.</p><ul>{item.plan_json.steps.map(step => { const presentation = capabilityPresentation(step.capability_id); return <li key={step.step_id}><strong>{presentation.label}</strong><span>{presentation.description}</span><code>{step.capability_id}</code></li> })}</ul><button type="button" className="button button-primary" disabled={submitting} onClick={() => void approve()}>{submitting ? 'Approving...' : 'Approve & Execute'}</button><button type="button" className="button button-danger" disabled={submitting} onClick={() => void onReject(approvalId, 'Plan requires operator changes')}>Reject</button></div>
}

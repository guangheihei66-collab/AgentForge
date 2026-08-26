import { capabilityPresentation } from '../agent/capabilities'
import type { ApprovalQueueItem } from '../types'

export function AgentApprovalCard({ item, onApprove, onReject }: { item: ApprovalQueueItem; onApprove: (approvalId: string) => Promise<void>; onReject: (approvalId: string, reason: string) => Promise<void> }) {
  const approvalId = item.approval_id ?? item.id
  return <div className="panel"><div className="panel-title"><h3>Approval required</h3><span>Plan v{item.plan_version}</span></div><p>{item.plan_json.summary ?? 'Review this governed plan before execution.'}</p><p>Workspace: {item.resolved_snapshot?.project_authority?.canonical_workspace_root ?? 'Selected Project workspace'}</p><p>Risk: read-only governed capabilities. Arbitrary shell execution is not granted.</p><ul>{item.plan_json.steps.map(step => { const presentation = capabilityPresentation(step.capability_id); return <li key={step.step_id}><strong>{presentation.label}</strong><span>{presentation.description}</span><code>{step.capability_id}</code></li> })}</ul><button className="button button-primary" onClick={() => void onApprove(approvalId)}>Approve</button><button className="button button-danger" onClick={() => void onReject(approvalId, 'Plan requires operator changes')}>Reject</button></div>
}

import { AlertTriangle, Ban, CheckCircle2, FileText, ShieldCheck, XCircle } from 'lucide-react'
import { PermissionPill, RiskPill, StatusPill } from '../components/StatusPill'
import { PanelTitle } from './Dashboard'
import type { ApprovalQueueItem, ResolvedExecutionSnapshot } from '../types'

const permission = (snapshot: ResolvedExecutionSnapshot) => snapshot.capability_id === 'test_verification' ? 'APPROVED_EXEC' : 'SAFE_READ'
const risk = (snapshot: ResolvedExecutionSnapshot) => snapshot.capability_id === 'repository_state' ? 'low' : 'medium'
const parameters = (snapshot: ResolvedExecutionSnapshot) => Object.entries(snapshot.normalized_parameters).map(([key, value]) => `${key}: ${value}`).join(', ') || 'none'

export function Approvals({ approvals, actionError, onApprove, onReject, onCancel }: { approvals: ApprovalQueueItem[]; actionError?: string | null; onApprove: (id: string) => void; onReject: (id: string) => void; onCancel: () => void }) {
  const selected = approvals[0]
  const snapshots = selected?.resolved_snapshot?.steps ?? []
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">HUMAN CONTROL POINT</div><h2>Approval Center</h2><p>Review exactly what the Agent will execute before it receives permission.</p></div><div className="approval-count"><span>{approvals.length}</span> pending</div></div>
    {actionError && <div className="callout" role="alert"><AlertTriangle size={18} /><div><strong>Decision failed</strong><span>{actionError}</span></div></div>}
    {selected ? <div className="approval-layout">
      <div className="panel plan-panel">
        <div className="callout"><ShieldCheck size={22} /><div><strong>This is what the Agent will execute.</strong><span>Review the capability, resolved tool, normalized parameters, and registry binding.</span></div></div>
        <PanelTitle title={`Resolved plan · Version ${selected.plan_version}`} action={`${snapshots.length} steps`} />
        <div className="plan-list">{snapshots.map((snapshot, index) => <div className="plan-step" key={snapshot.step_id}>
          <span className="step-number">{index + 1}</span>
          <div className="step-tool"><FileText size={17} /><strong>{snapshot.capability_id}</strong><span>Resolved tool: {snapshot.resolved_tool_id} · {snapshot.resolved_action}</span><PermissionPill value={permission(snapshot)} /></div>
          <div className="step-risk"><span>Normalized parameters</span><strong>{parameters(snapshot)}</strong><RiskPill value={risk(snapshot)} /></div>
          <div className="step-evidence"><span>Registry fingerprint:</span><strong>{snapshot.registry_fingerprint.slice(0, 12)}</strong></div>
        </div>)}</div>
        <div className="plan-footer"><span><AlertTriangle size={15} /> Capability, tool, parameters, and registry semantics are approval-bound.</span><strong>Aggregate risk: <RiskPill value="Medium" /></strong></div>
      </div>
      <aside className="panel decision-panel"><div className="decision-header"><StatusPill status="WAITING_APPROVAL" /><span>Plan v{selected.plan_version}</span></div><h3>{selected.task_title}</h3><p className="muted">Requested by {selected.requested_by}</p><div className="boundary"><span>Permission boundary</span><strong>Workspace-scoped only</strong><small>No shell access · no destructive actions · no secret files</small></div><div className="permission-list"><div><PermissionPill value="SAFE_READ" /><span>Repository and file metadata</span></div><div><PermissionPill value="APPROVED_EXEC" /><span>Predefined test profile</span></div></div><div className="decision-actions"><button type="button" className="button button-approve" onClick={() => onApprove(selected.id)}><CheckCircle2 size={16} /> Approve</button><button type="button" className="button button-danger" onClick={() => onReject(selected.id)}><XCircle size={16} /> Reject</button><button type="button" className="button button-muted" onClick={onCancel}><Ban size={16} /> Cancel task</button></div><p className="audit-note">Your decision will be recorded in the audit log.</p></aside>
    </div> : <div className="panel empty-state large">No pending approvals. Tasks will appear here after their plans are validated.</div>}
  </section>
}

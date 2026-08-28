import { AlertTriangle, Ban, Bot, CheckCircle2, FileText, ShieldCheck, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PermissionPill, RiskPill, StatusPill } from '../components/StatusPill'
import { isAgentManagedApproval } from '../agent/approval-classification'
import { PanelTitle } from './Dashboard'
import type { ApprovalQueueItem, ResolvedExecutionSnapshot } from '../types'

const permission = (snapshot: ResolvedExecutionSnapshot) => snapshot.capability_id === 'test_verification' ? 'APPROVED_EXEC' : 'SAFE_READ'
const risk = (snapshot: ResolvedExecutionSnapshot) => snapshot.capability_id === 'repository_state' ? 'low' : 'medium'
const parameters = (snapshot: ResolvedExecutionSnapshot, empty: string) => Object.entries(snapshot.normalized_parameters).map(([key, value]) => `${key}: ${value}`).join(', ') || empty

export function Approvals({ approvals, actionError, onApprove, onReject, onCancel, onOpenInAgentWorkspace }: { approvals: ApprovalQueueItem[]; actionError?: string | null; onApprove: (id: string) => void; onReject: (id: string) => void; onCancel: () => void; onOpenInAgentWorkspace: (taskId: string) => void }) {
  const { t } = useTranslation()
  const selected = approvals[0]
  const snapshots = selected?.resolved_snapshot?.steps ?? []
  const agentManaged = selected ? isAgentManagedApproval(selected) : false
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">{t('approvals.eyebrow')}</div><h2>{t('approvals.title')}</h2><p>{t('approvals.subtitle')}</p></div><div className="approval-count"><span>{approvals.length}</span> {t('approvals.pending')}</div></div>
    {actionError && <div className="callout" role="alert"><AlertTriangle size={18} /><div><strong>{t('approvals.decisionFailed')}</strong><span>{actionError}</span></div></div>}
    {selected ? <div className="approval-layout">
      <div className="panel plan-panel">
        <div className="callout"><ShieldCheck size={22} /><div><strong>{t('approvals.executeNotice')}</strong><span>{t('approvals.reviewNotice')}</span></div></div>
        <PanelTitle title={`${t('approvals.resolvedPlan')} · ${t('common.labels.version')} ${selected.plan_version}`} action={t('approvals.steps', { count: snapshots.length })} />
        <div className="plan-list">{snapshots.map((snapshot, index) => <div className="plan-step" key={snapshot.step_id}>
          <span className="step-number">{index + 1}</span>
          <div className="step-tool"><FileText size={17} /><strong>{snapshot.capability_id}</strong><span>{t('approvals.resolvedTool')}: {snapshot.resolved_tool_id} · {snapshot.resolved_action}</span><PermissionPill value={permission(snapshot)} /></div>
          <div className="step-risk"><span>{t('approvals.normalized')}</span><strong>{parameters(snapshot, t('common.states.noParameters'))}</strong><RiskPill value={risk(snapshot)} /></div>
          <div className="step-evidence"><span>{t('approvals.fingerprint')}</span><strong>{snapshot.registry_fingerprint.slice(0, 12)}</strong></div>
        </div>)}</div>
        <div className="plan-footer"><span><AlertTriangle size={15} /> {t('approvals.bindingNotice')}</span><strong>{t('approvals.aggregateRisk')} <RiskPill value="Medium" /></strong></div>
      </div>
      <aside className="panel decision-panel"><div className="decision-header"><StatusPill status="WAITING_APPROVAL" /><span>{t('agentPlan.planVersion', { version: selected.plan_version })}</span></div><h3>{selected.task_title}</h3><p className="muted">{t('approvals.requestedBy')} {selected.requested_by}</p><div className="boundary"><span>{t('approvals.boundary')}</span><strong>{t('approvals.workspaceOnly')}</strong><small>{t('approvals.noShell')}</small></div><div className="permission-list"><div><PermissionPill value="SAFE_READ" /><span>{t('capabilities.repository_state.label')} / {t('capabilities.project_metadata.label')}</span></div><div><PermissionPill value="APPROVED_EXEC" /><span>{t('capabilities.test_verification.label')}</span></div></div>{agentManaged ? <div className="approval-only-note" role="note"><Bot size={16} /><span>{t('approvals.agentWorkspaceNote')}</span></div> : <div className="approval-only-note" role="note"><AlertTriangle size={16} /><span>{t('approvals.approvalOnlyNote')}</span></div>}<div className="decision-actions">{agentManaged ? <button type="button" className="button button-primary" onClick={() => onOpenInAgentWorkspace(selected.task_id)}><Bot size={16} /> {t('approvals.openInAgentWorkspace')}</button> : <button type="button" className="button button-approve" onClick={() => onApprove(selected.id)}><CheckCircle2 size={16} /> {t('common.actions.approveOnly')}</button>}<button type="button" className="button button-danger" onClick={() => onReject(selected.id)}><XCircle size={16} /> {t('common.actions.reject')}</button><button type="button" className="button button-muted" onClick={onCancel}><Ban size={16} /> {t('common.actions.cancel')} {t('common.labels.task')}</button></div><p className="audit-note">{t('approvals.auditNote')}</p></aside>
    </div> : <div className="panel empty-state large">{t('approvals.empty')}</div>}
  </section>
}

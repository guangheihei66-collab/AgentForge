import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { capabilityDescriptionKey, capabilityLabelKey } from '../i18n/status'
import type { ApprovalQueueItem } from '../types'

export function AgentApprovalCard({ item, onApprove, onReject }: { item: ApprovalQueueItem; onApprove: (item: ApprovalQueueItem) => Promise<void>; onReject: (approvalId: string, reason: string) => Promise<void> }) {
  const { t } = useTranslation()
  const approvalId = item.approval_id ?? item.id
  const [submitting, setSubmitting] = useState(false)
  async function approve() {
    if (submitting) return
    setSubmitting(true)
    try { await onApprove(item) } finally { setSubmitting(false) }
  }
  return <div className="panel"><div className="panel-title"><h3>{t('agentApproval.required')}</h3><span>{t('agentApproval.planVersion', { version: item.plan_version })}</span></div><p>{item.plan_json.summary ?? t('agentApproval.reviewPlan')}</p><p>{t('common.labels.workspace')}: {item.resolved_snapshot?.project_authority?.canonical_workspace_root ?? t('agentApproval.selectedWorkspace')}</p><p>{t('agentApproval.risk')}</p><ul>{item.plan_json.steps.map(step => <li key={step.step_id}><strong>{t(capabilityLabelKey(step.capability_id))}</strong><span>{t(capabilityDescriptionKey(step.capability_id))}</span><code>{step.capability_id}</code></li>)}</ul><button type="button" className="button button-primary" disabled={submitting} onClick={() => void approve()}>{submitting ? t('agentApproval.approving') : t('common.actions.approveAndExecute')}</button><button type="button" className="button button-danger" disabled={submitting} onClick={() => void onReject(approvalId, t('agentApproval.rejectReason'))}>{t('agentApproval.reject')}</button></div>
}

import { useEffect, useState } from 'react'
import { ArrowLeft, FileSearch, History, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { StatusPill } from '../components/StatusPill'
import { Timeline } from '../components/Timeline'
import { PanelTitle } from './Dashboard'
import type { TaskDetail as Detail } from '../types'
import type { ReconciliationEligibility } from '../types'
import { api } from '../api/client'

export function TaskDetail({ detail, reconciliation: supplied, onReconcile, onBack, onReport }: { detail: Detail; reconciliation?: ReconciliationEligibility; onReconcile?: () => void | Promise<void>; onBack: () => void; onReport: () => void }) {
  const { t, i18n } = useTranslation()
  const [reconciliation, setReconciliation] = useState<ReconciliationEligibility | undefined>(supplied)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    setReconciliation(supplied)
    if (supplied) return
    let current = true
    void api.getReconciliationEligibility(detail.task.id).then(value => { if (current) setReconciliation(value) }).catch(() => undefined)
    return () => { current = false }
  }, [detail.task.id, supplied])
  async function reconcile() {
    if (!reconciliation?.eligible || busy) return
    setBusy(true); setMessage('')
    try {
      if (onReconcile) await onReconcile()
      else await api.reconcileTask(detail.task.id)
      setReconciliation({ task_id: detail.task.id, eligible: false, reason_code: 'TASK_ALREADY_RECONCILED' })
      setMessage(t('taskReconciliation.succeeded'))
    } catch {
      setMessage(t('taskReconciliation.refused'))
    } finally { setBusy(false) }
  }
  const task = detail.task; const plan = detail.plans[0]
  return <section className="page-stack">
    <button className="back-button" onClick={onBack}><ArrowLeft size={15} /> {t('tasks.backToDashboard')}</button>
    <div className="page-heading task-heading"><div><div className="eyebrow">{t('tasks.detailEyebrow')}</div><h2>{task.title}</h2><p>{task.goal}</p></div><StatusPill status={task.status} /></div>
    {reconciliation?.eligible && <div className="panel" role="alert"><strong>{t('taskReconciliation.detected')}</strong><p>{t('taskReconciliation.description')}</p><button className="button button-secondary" disabled={busy} onClick={() => void reconcile()}>{t('taskReconciliation.action')}</button></div>}
    {message && <div role="status">{message}</div>}
    <div className="panel"><div className="task-meta"><div><span>{t('tasks.workspace')}</span><strong>{task.workspace}</strong></div><div><span>{t('tasks.created')}</span><strong>{new Date(task.created_at).toLocaleString(i18n.language)}</strong></div><div><span>{t('tasks.agent')}</span><strong>{t('tasks.releaseVerificationAgent')}</strong></div><button className="button button-secondary" onClick={onReport}>{t('tasks.openReport')}</button></div><Timeline current={task.status} /></div>
    <div className="content-grid detail-grid"><div className="panel"><PanelTitle title={`${t('tasks.generatedPlan')} · ${t('tasks.version')} ${plan?.version ?? '—'}`} action={plan ? plan.validation_status : t('common.states.noPlan')} />{plan ? <div className="compact-plan">{plan.plan_json.resolved_steps.map((snapshot, index) => <div className="compact-step" key={snapshot.step_id}><span className="step-number">{index + 1}</span><div><strong>{snapshot.capability_id}</strong><span>{snapshot.resolved_tool_id} · {snapshot.resolved_action}</span></div><span>{Object.entries(snapshot.normalized_parameters).map(([key, value]) => `${key}: ${value}`).join(', ') || t('common.states.noParameters')}</span></div>)}</div> : <div className="empty-state">{t('common.states.noValidatedPlan')}</div>}</div><div className="panel"><PanelTitle title={t('tasks.evidence')} action={t('tasks.artifacts', { count: detail.evidence.length })} />{detail.evidence.length ? detail.evidence.map(item => <div className="evidence-row" key={item.id}><FileSearch size={16} /><div><strong>{item.summary}</strong><span>{item.artifact_path}</span></div></div>) : <div className="empty-state">{t('tasks.evidenceAfter')}</div>}</div></div>
    <div className="content-grid detail-grid"><div className="panel"><PanelTitle title={t('tasks.toolExecutions')} action={t('tasks.recorded', { count: detail.executions.length })} />{detail.executions.length ? detail.executions.map(item => <div className="execution-row" key={item.id}><span className={`execution-icon ${item.status.toLowerCase()}`}><Play size={14} /></span><div><strong>{item.tool_name} · {item.action}</strong><span>{item.result_summary ?? t('tasks.noResult')}</span></div><StatusPill status={item.status} /></div>) : <div className="empty-state">{t('tasks.noExecution')}</div>}</div><div className="panel"><PanelTitle title={t('tasks.auditHistory')} action={t('tasks.events', { count: detail.audit.length })} />{detail.audit.map(item => <div className="audit-row" key={item.id}><History size={14} /><div><strong>{item.event_type.replaceAll('_', ' ')}</strong><span>{item.actor} · {item.payload_summary}</span></div><time>{new Date(item.created_at).toLocaleTimeString(i18n.language)}</time></div>)}</div></div>
  </section>
}

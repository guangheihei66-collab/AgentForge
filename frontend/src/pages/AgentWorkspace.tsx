import { useState, type FormEvent } from 'react'
import { Bot, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ApprovalQueueItem, ProjectSummary, Report, TaskDetail, TaskSummary } from '../types'
import { agentStatusKey } from '../i18n/status'
import { useAgentTaskPolling } from '../agent/polling'
import { canResumeApprovedExecution } from '../agent/recovery'
import { AgentApprovalCard } from '../components/AgentApprovalCard'
import { AgentPlanCard } from '../components/AgentPlanCard'
import { buildAgentTimeline } from '../agent/timeline'
import { AgentTimeline } from '../components/AgentTimeline'
import { AgentReportCard } from '../components/AgentReportCard'

export function AgentWorkspace({ projects, planning, error, onStart, approvals = [], task, detail, report, onRefreshTask, onApprove, onReject, onExecute }: {
  projects: ProjectSummary[]
  planning: boolean
  error: string | null
  onStart: (projectId: string, goal: string) => Promise<void>
  approvals?: ApprovalQueueItem[]
  task?: TaskSummary
  detail?: TaskDetail
  report?: Report
  onRefreshTask?: (taskId: string) => Promise<unknown>
  onApprove?: (item: ApprovalQueueItem) => Promise<void>
  onReject?: (approvalId: string, reason: string) => Promise<void>
  onExecute?: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [projectId, setProjectId] = useState('')
  const [goal, setGoal] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const polling = useAgentTaskPolling(task?.id, task?.status, onRefreshTask ? async (taskId) => { await onRefreshTask(taskId) } : async () => undefined)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!projectId || !goal.trim() || submitting || planning) return
    setSubmitting(true)
    try { await onStart(projectId, goal) } finally { setSubmitting(false) }
  }
  const currentPlan = detail?.plans.reduce((latest, candidate) => !latest || candidate.version > latest.version ? candidate : latest, undefined as TaskDetail['plans'][number] | undefined)
  const currentApproval = task && currentPlan ? approvals.find(item => item.task_id === task.id && item.plan_id === currentPlan.id && item.plan_version === currentPlan.version && item.decision === 'PENDING') : undefined
  const canResume = canResumeApprovedExecution({ task, detail, currentPlan })
  const planningFailed = task?.status === 'FAILED' && !currentPlan
  const statusLabel = planning ? t('agent.status.planning') : task?.status ? t(agentStatusKey(task.status)) : undefined
  const nextAction = planning ? t('agent.planningNext') : task?.status === 'WAITING_APPROVAL' ? t('agent.waitingNext') : task?.status === 'RUNNING' ? t('agent.runningNext') : task?.status === 'SUCCESS' ? t('agent.successNext') : task?.status === 'FAILED' ? (planningFailed ? t('agent.planningFailed') : t('agent.failedNext')) : t('agent.startNext')
  const timeline = detail && report ? buildAgentTimeline({ detail, report, pendingApproval: approvals[0], transientPlanning: planning }) : []
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">{t('agent.eyebrow')}</div><h2>{t('agent.title')}</h2><p>{t('agent.description')}</p></div><Bot size={30} /></div>
    {task ? <div className="panel" aria-label={t('agent.currentRun')}><div className="panel-title"><h3>{t('agent.currentRun')}</h3><span>{statusLabel ?? t('agent.status.unknown')}</span></div><p><strong>{t('common.labels.project')}:</strong> {projects.find(project => project.id === task.project_id)?.name ?? task.project_id ?? t('common.labels.unknown')}</p><p><strong>{t('common.labels.task')}:</strong> <code>{task.id}</code></p>{currentPlan && <p><strong>{t('agent.planVersion')}:</strong> v{currentPlan.version}</p>}<p>{nextAction}</p></div> : !planning && <div className="panel" aria-label={t('agent.noCurrentRun')}><h3>{t('agent.noCurrentRun')}</h3><p>{t('agent.createToBegin')}</p></div>}
    <form className="panel" onSubmit={submit}>
      <div className="panel-title"><h3>{t('agent.goalComposer')}</h3><span>{t('agent.authorityRequired')}</span></div>
      <label>{t('common.labels.project')}<select aria-label={t('agent.selectProject')} value={projectId} onChange={event => setProjectId(event.target.value)} required><option value="">{t('agent.selectProject')}</option>{projects.filter(project => project.status === 'ACTIVE').map(project => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
      <label>{t('agent.goal')}<textarea aria-label={t('agent.goal')} value={goal} onChange={event => setGoal(event.target.value)} placeholder={t('agent.goalPlaceholder')} required /></label>
      <button className="button button-primary" disabled={submitting || planning || !projectId || !goal.trim()}><Play size={15} /> {planning ? t('agent.starting') : t('agent.start')}</button>
      {planningFailed ? <div className="form-message" role="alert">{t('agent.planningFailed')}</div> : error && <div className="form-message" role="alert">{error}</div>}
      {polling.refreshError && <div className="form-message" role="status">{t('agent.refreshError')}: {polling.refreshError}</div>}
    </form>
    {currentPlan && <AgentPlanCard plan={currentPlan} rawGoal={detail?.task.goal ?? ''} />}
    {currentApproval && onApprove && onReject && <AgentApprovalCard item={currentApproval} onApprove={onApprove} onReject={onReject} />}
    {canResume && onExecute && <div className="panel"><div className="panel-title"><h3>{t('agent.execution')}</h3><span>{t('agent.governedExecution')}</span></div><p>{t('agent.recoveryDescription')}</p><button type="button" className="button button-primary" onClick={() => void onExecute()}>{t('common.actions.resumeApprovedExecution')}</button></div>}
    {detail && report ? <AgentTimeline entries={timeline} /> : !planning && <div className="panel"><div className="panel-title"><h3>{t('agent.timeline')}</h3><span>{t('agent.authoritativeLifecycle')}</span></div><p>{t('agent.timelineEmpty')}</p></div>}
    {detail && report && <AgentReportCard detail={detail} report={report} />}
  </section>
}

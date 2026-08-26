import { useState, type FormEvent } from 'react'
import { Bot, Play } from 'lucide-react'
import type { ApprovalQueueItem, ProjectSummary, Report, TaskDetail, TaskSummary } from '../types'
import { useAgentTaskPolling } from '../agent/polling'
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
  onRefreshTask?: (taskId: string) => Promise<void>
  onApprove?: (approvalId: string) => Promise<void>
  onReject?: (approvalId: string, reason: string) => Promise<void>
  onExecute?: () => Promise<void>
}) {
  const [projectId, setProjectId] = useState('')
  const [goal, setGoal] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const polling = useAgentTaskPolling(task?.id, task?.status, onRefreshTask ?? (async () => undefined))
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!projectId || !goal.trim() || submitting || planning) return
    setSubmitting(true)
    try { await onStart(projectId, goal) } finally { setSubmitting(false) }
  }
  const currentPlan = detail?.plans.reduce((latest, candidate) => !latest || candidate.version > latest.version ? candidate : latest, undefined as TaskDetail['plans'][number] | undefined)
  const timeline = detail && report ? buildAgentTimeline({ detail, report, pendingApproval: approvals[0], transientPlanning: planning }) : []
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">REPOSITORY ANALYST AGENT</div><h2>Agent workspace</h2><p>Perform governed repository analysis with human approval.</p></div><Bot size={30} /></div>
    <form className="panel" onSubmit={submit}>
      <div className="panel-title"><h3>Goal Composer</h3><span>Project authority required</span></div>
      <label>Project<select aria-label="Project" value={projectId} onChange={event => setProjectId(event.target.value)} required><option value="">Select a Project</option>{projects.filter(project => project.status === 'ACTIVE').map(project => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
      <label>Goal<textarea aria-label="Goal" value={goal} onChange={event => setGoal(event.target.value)} placeholder="Check whether this project is ready to release." required /></label>
      <button className="button button-primary" disabled={submitting || planning || !projectId || !goal.trim()}><Play size={15} /> {planning ? 'Planning...' : 'Start Agent'}</button>
      {error && <div className="form-message" role="alert">{error}</div>}
      {polling.refreshError && <div className="form-message" role="status">Unable to refresh Agent status: {polling.refreshError}</div>}
    </form>
    {currentPlan && <AgentPlanCard plan={currentPlan} rawGoal={detail?.task.goal ?? ''} />}
    {approvals[0] && onApprove && onReject && <AgentApprovalCard item={approvals[0]} onApprove={onApprove} onReject={onReject} />}
    {detail?.approvals.some(approval => approval.decision === 'APPROVED' && approval.plan_id === currentPlan?.id && approval.plan_version === currentPlan?.version) && onExecute && <div className="panel"><div className="panel-title"><h3>Execution</h3><span>Explicit operator action</span></div><p>The current Plan has an authoritative approval. Execution has not started automatically.</p><button className="button button-primary" onClick={() => void onExecute()}>Execute approved Plan</button></div>}
    {detail && report ? <AgentTimeline entries={timeline} /> : !planning && <div className="panel"><div className="panel-title"><h3>Agent Timeline</h3><span>Authoritative lifecycle</span></div><p>Start an Agent to see the persisted Plan, Approval, execution, observations, and Evidence.</p></div>}
    {detail && report && <AgentReportCard detail={detail} report={report} />}
  </section>
}

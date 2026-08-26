import { useState, type FormEvent } from 'react'
import { ArrowRight, Bot, Play } from 'lucide-react'
import type { ApprovalQueueItem, ProjectSummary } from '../types'

export function AgentWorkspace({ projects, planning, error, onStart, approvals = [], onApprove, onReject }: {
  projects: ProjectSummary[]
  planning: boolean
  error: string | null
  onStart: (projectId: string, goal: string) => Promise<void>
  approvals?: ApprovalQueueItem[]
  onApprove?: (approvalId: string) => Promise<void>
  onReject?: (approvalId: string, reason: string) => Promise<void>
}) {
  const [projectId, setProjectId] = useState('')
  const [goal, setGoal] = useState('')
  const [submitting, setSubmitting] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!projectId || !goal.trim() || submitting || planning) return
    setSubmitting(true)
    try { await onStart(projectId, goal) } finally { setSubmitting(false) }
  }
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">REPOSITORY ANALYST AGENT</div><h2>Agent workspace</h2><p>Perform governed repository analysis with human approval.</p></div><Bot size={30} /></div>
    <form className="panel" onSubmit={submit}>
      <div className="panel-title"><h3>Goal Composer</h3><span>Project authority required</span></div>
      <label>Project<select aria-label="Project" value={projectId} onChange={event => setProjectId(event.target.value)} required><option value="">Select a Project</option>{projects.filter(project => project.status === 'ACTIVE').map(project => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
      <label>Goal<textarea aria-label="Goal" value={goal} onChange={event => setGoal(event.target.value)} placeholder="Check whether this project is ready to release." required /></label>
      <button className="button button-primary" disabled={submitting || planning || !projectId || !goal.trim()}><Play size={15} /> {planning ? 'Planning...' : 'Start Agent'}</button>
      {error && <div className="form-message" role="alert">{error}</div>}
    </form>
    <div className="content-grid dashboard-grid"><div className="panel"><div className="panel-title"><h3>Agent Timeline</h3><span>Authoritative lifecycle</span></div><p>Start an Agent to see the persisted Plan, Approval, execution, observations, and Evidence.</p></div><div className="panel"><div className="panel-title"><h3>Approval</h3><span>{approvals.length ? `${approvals.length} pending` : 'No pending approval'}</span></div>{approvals.map(item => <div key={item.id}><strong>{item.task_title}</strong><span>Plan v{item.plan_version}</span><button className="text-button" onClick={() => onApprove?.(item.approval_id ?? item.id)}>Approve <ArrowRight size={14} /></button><button className="text-button" onClick={() => onReject?.(item.approval_id ?? item.id, 'Plan requires operator changes')}>Reject</button></div>)}</div></div>
  </section>
}

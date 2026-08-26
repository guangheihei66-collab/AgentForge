import type { AgentTimelineEntry } from '../agent/types'

const labels: Record<AgentTimelineEntry['kind'], string> = {
  GOAL_RECEIVED: 'Goal received', PLANNING: 'Planning', PLAN_CREATED: 'Plan created', WAITING_APPROVAL: 'Waiting for approval', APPROVED: 'Approved', APPROVAL_REJECTED: 'Approval rejected', STEP_STARTED: 'Step started', TOOL_EXECUTION_COMPLETED: 'Tool execution completed', OBSERVATION_RECORDED: 'Observation recorded', STEP_FAILED: 'Step failed', REPLANNING: 'Replanning', SUCCESSOR_PLAN_CREATED: 'Successor plan created', COMPLETED: 'Completed', FAILED: 'Failed',
}

export function AgentTimeline({ entries }: { entries: AgentTimelineEntry[] }) {
  return <div className="panel"><div className="panel-title"><h3>Agent Timeline</h3><span>{entries.length} events</span></div>{entries.length === 0 ? <p>No persisted Agent events yet.</p> : <ol>{entries.map(entry => <li key={entry.id}><strong>{labels[entry.kind]}</strong>{entry.planVersion && <span>Plan v{entry.planVersion}</span>}<span>{entry.summary}</span><time>{new Date(entry.timestamp).toLocaleString()}</time></li>)}</ol>}</div>
}

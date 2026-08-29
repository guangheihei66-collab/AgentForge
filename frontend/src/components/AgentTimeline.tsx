import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentTimelineEntry } from '../agent/types'

const labels: Record<AgentTimelineEntry['kind'], string> = {
  GOAL_RECEIVED: 'timeline.goalReceived', PLANNING: 'timeline.planning', PLAN_CREATED: 'timeline.planCreated', WAITING_APPROVAL: 'timeline.waitingApproval', APPROVED: 'timeline.approved', APPROVAL_REJECTED: 'timeline.approvalRejected', STEP_STARTED: 'timeline.stepStarted', TOOL_EXECUTION_COMPLETED: 'timeline.toolExecutionCompleted', OBSERVATION_RECORDED: 'timeline.observationRecorded', STEP_FAILED: 'timeline.stepFailed', REPLANNING: 'timeline.replanning', SUCCESSOR_PLAN_CREATED: 'timeline.successorPlanCreated', COMPLETED: 'timeline.completed', FAILED: 'timeline.failed', UNKNOWN_EVENT: 'timeline.unknownEvent',
}

export function AgentTimeline({ entries }: { entries: AgentTimelineEntry[] }) {
  const { t, i18n } = useTranslation()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  return <div className="panel"><div className="panel-title"><h3>{t('timeline.title')}</h3><span>{t('timeline.events', { count: entries.length })}</span></div>{entries.length === 0 ? <p>{t('timeline.noEvents')}</p> : <ol className="agent-timeline-list">{entries.map(entry => {
    const title = t(labels[entry.kind])
    return <li className="agent-timeline-row" key={entry.id}>
    <span className="agent-timeline-marker" aria-hidden="true" />
    <div className="agent-timeline-content">
      <div className="agent-timeline-heading"><strong>{title}</strong><span className="agent-timeline-status">{entry.status}</span></div>
      {entry.planVersion && <span className="agent-timeline-plan">{t('agentPlan.planVersion', { version: entry.planVersion })}</span>}
      {entry.stepId && <span className="agent-timeline-step">{entry.stepId}</span>}
      {entry.summary && entry.summary !== title && <p className="agent-timeline-summary">{entry.summary}</p>}
      <time className="agent-timeline-time" dateTime={entry.timestamp}>{new Date(entry.timestamp).toLocaleString(i18n.language)}</time>
      {entry.raw && <div className="agent-timeline-details"><button type="button" aria-expanded={Boolean(expanded[entry.id])} onClick={() => setExpanded(value => ({ ...value, [entry.id]: !value[entry.id] }))}>{expanded[entry.id] ? t('common.actions.hideTechnicalDetails') : t('common.actions.showTechnicalDetails')}</button>{expanded[entry.id] && <pre>{JSON.stringify(entry.raw, null, 2)}</pre>}</div>}
    </div>
  </li>
  })}</ol>}</div>
}

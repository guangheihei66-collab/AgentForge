import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentTimelineEntry } from '../agent/types'

const labels: Record<AgentTimelineEntry['kind'], string> = {
  GOAL_RECEIVED: 'timeline.goalReceived', PLANNING: 'timeline.planning', PLAN_CREATED: 'timeline.planCreated', WAITING_APPROVAL: 'timeline.waitingApproval', APPROVED: 'timeline.approved', APPROVAL_REJECTED: 'timeline.approvalRejected', STEP_STARTED: 'timeline.stepStarted', TOOL_EXECUTION_COMPLETED: 'timeline.toolExecutionCompleted', OBSERVATION_RECORDED: 'timeline.observationRecorded', STEP_FAILED: 'timeline.stepFailed', REPLANNING: 'timeline.replanning', SUCCESSOR_PLAN_CREATED: 'timeline.successorPlanCreated', COMPLETED: 'timeline.completed', FAILED: 'timeline.failed',
}

export function AgentTimeline({ entries }: { entries: AgentTimelineEntry[] }) {
  const { t, i18n } = useTranslation()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  return <div className="panel"><div className="panel-title"><h3>{t('timeline.title')}</h3><span>{t('timeline.events', { count: entries.length })}</span></div>{entries.length === 0 ? <p>{t('timeline.noEvents')}</p> : <ol>{entries.map(entry => <li key={entry.id}><strong>{t(labels[entry.kind])}</strong>{entry.planVersion && <span>{t('agentPlan.planVersion', { version: entry.planVersion })}</span>}<span>{entry.summary}</span><time>{new Date(entry.timestamp).toLocaleString(i18n.language)}</time>{entry.raw && <><button type="button" aria-expanded={Boolean(expanded[entry.id])} onClick={() => setExpanded(value => ({ ...value, [entry.id]: !value[entry.id] }))}>{expanded[entry.id] ? t('common.actions.hideTechnicalDetails') : t('common.actions.showTechnicalDetails')}</button>{expanded[entry.id] && <pre>{JSON.stringify(entry.raw, null, 2)}</pre>}</>}</li>)}</ol>}</div>
}

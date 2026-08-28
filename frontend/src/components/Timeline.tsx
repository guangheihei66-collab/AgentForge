import { Check, Circle, Clock3, Play } from 'lucide-react'
import type { TaskStatus } from '../types'
import { useTranslation } from 'react-i18next'
import { taskStatusKey } from '../i18n/status'

const states: TaskStatus[] = ['CREATED', 'PLANNING', 'WAITING_APPROVAL', 'RUNNING', 'SUCCESS']
export function Timeline({ current }: { current: TaskStatus }) {
  const { t } = useTranslation()
  const currentIndex = states.indexOf(current)
  return <div className="timeline">{states.map((state, index) => { const done = index < currentIndex || current === 'SUCCESS'; const active = state === current; const Icon = done ? Check : active ? Clock3 : state === 'RUNNING' ? Play : Circle; return <div className={`timeline-step ${done ? 'done' : ''} ${active ? 'active' : ''}`} key={state}><div className="timeline-icon"><Icon size={15} /></div><span>{t(taskStatusKey(state))}</span>{index < states.length - 1 && <i className={done ? 'filled' : ''} />}</div> })}</div>
}

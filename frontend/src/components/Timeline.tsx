import { Check, Circle, Clock3, Play } from 'lucide-react'
import type { TaskStatus } from '../types'

const states: TaskStatus[] = ['CREATED', 'PLANNING', 'WAITING_APPROVAL', 'RUNNING', 'SUCCESS']
export function Timeline({ current }: { current: TaskStatus }) {
  const currentIndex = states.indexOf(current)
  return <div className="timeline">{states.map((state, index) => { const done = index < currentIndex || current === 'SUCCESS'; const active = state === current; const Icon = done ? Check : active ? Clock3 : state === 'RUNNING' ? Play : Circle; return <div className={`timeline-step ${done ? 'done' : ''} ${active ? 'active' : ''}`} key={state}><div className="timeline-icon"><Icon size={15} /></div><span>{state.replace('_', ' ')}</span>{index < states.length - 1 && <i className={done ? 'filled' : ''} />}</div> })}</div>
}
